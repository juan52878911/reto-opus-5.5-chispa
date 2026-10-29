import XCTest
@testable import Chispa

/// Hallazgos R1 #2, #3, #8 y #14: cachés por hash y atómicas, τ de L2c, errores de capa visibles, torres que fallan.
final class CacheYErroresTests: XCTestCase {
    var dir: URL!

    override func setUpWithError() throws {
        dir = FileManager.default.temporaryDirectory.appendingPathComponent("chispa-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: dir) }

    private func modelo() throws -> String {
        let r = dir.appendingPathComponent("m.chispa").path
        try Data("x".utf8).write(to: URL(fileURLWithPath: r))
        return r
    }

    private func ficheros() -> [String] { ((try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []).sorted() }

    // --- #3: el ONNX de L2 se identifica por el hash de la sección y se escribe de forma atómica ---

    func testDosModelosDelMismoTamanoNoComparteOnnxDeL2() throws {
        let a = MotorFalso(); a.hashes = [seccionL2: "aaa"]; a.alExtraer = { try Data("A".utf8).write(to: URL(fileURLWithPath: $0)) }
        let b = MotorFalso(); b.hashes = [seccionL2: "bbb"]; b.alExtraer = { try Data("B".utf8).write(to: URL(fileURLWithPath: $0)) }
        let m = try modelo()
        let ra = try CacheFicheros.rutaOnnxL2(motor: a, dir: dir, modelo: m)
        let rb = try CacheFicheros.rutaOnnxL2(motor: b, dir: dir, modelo: m)
        XCTAssertNotEqual(ra, rb)
        XCTAssertEqual(try String(contentsOfFile: ra), "A")
        XCTAssertEqual(try String(contentsOfFile: rb), "B")
        _ = try CacheFicheros.rutaOnnxL2(motor: a, dir: dir, modelo: m)
        XCTAssertEqual(a.extracciones, 1) // la segunda vez reutiliza
    }

    func testSiLaExtraccionMuereNoQuedaUnOnnxTruncadoConElNombreDefinitivo() throws {
        let m = MotorFalso(); m.hashes = [seccionL2: "h1"]
        m.alExtraer = { try Data("trunc".utf8).write(to: URL(fileURLWithPath: $0)); throw ErrorChispa("proceso muerto") }
        let ruta = try modelo()
        XCTAssertThrowsError(try CacheFicheros.rutaOnnxL2(motor: m, dir: dir, modelo: ruta))
        XCTAssertEqual(ficheros(), ["m.chispa"]) // ni el definitivo ni el .tmp
        m.alExtraer = { try Data("completo".utf8).write(to: URL(fileURLWithPath: $0)) }
        XCTAssertEqual(try String(contentsOfFile: try CacheFicheros.rutaOnnxL2(motor: m, dir: dir, modelo: ruta)), "completo")
    }

    func testSinHashDeSeccionElNombreSaleDelHashDelFichero() throws {
        let m = MotorFalso()
        m.alExtraer = { try Data("A".utf8).write(to: URL(fileURLWithPath: $0)) }
        let ruta = try CacheFicheros.rutaOnnxL2(motor: m, dir: dir, modelo: try modelo())
        XCTAssertTrue(ruta.hasSuffix("chispa-l2-\(CacheFicheros.sha256Hex(Data("x".utf8))).onnx"))
    }

    // --- #2: el ONNX de TORR se identifica por hash, no por tamaño ---

    func testDosTorresDelMismoTamanoYDistintoContenidoNoComparteFichero() throws {
        let ra = try CacheFicheros.rutaOnnxTorre(Data("AAAA".utf8), dir: dir)
        let rb = try CacheFicheros.rutaOnnxTorre(Data("BBBB".utf8), dir: dir)
        XCTAssertNotEqual(ra, rb)
        XCTAssertEqual(try String(contentsOfFile: ra), "AAAA")
        XCTAssertEqual(try String(contentsOfFile: rb), "BBBB")
        XCTAssertEqual(ficheros().count, 2) // sin temporales
        XCTAssertEqual(try CacheFicheros.rutaOnnxTorre(Data("AAAA".utf8), dir: dir), ra)
    }

    func testEscribirAtomicoLanzaSiElRenameFallaYNoDejaTemporales() throws {
        let destino = dir.appendingPathComponent("d")
        try FileManager.default.createDirectory(at: destino, withIntermediateDirectories: true)
        try Data("1".utf8).write(to: destino.appendingPathComponent("x"))
        // el destino es un directorio no vacío: rename(2) de un fichero sobre él falla
        XCTAssertThrowsError(try CacheFicheros.escribirAtomico(destino.path) { try Data("z".utf8).write(to: URL(fileURLWithPath: $0)) })
        XCTAssertEqual(ficheros(), ["d"])
    }

    // --- #8: τ de L2c ---

    private func l2c(tauConj: Double, conj: Bool = true) throws -> Respuesta {
        let m = MotorFalso()
        m.presentes = ["L2"]; m.calib = true; m.tau = 0.6; m.conj = conj; m.tauConj = tauConj
        m.l2 = { json("compra", 0.7, ["compra": 0.7]) }
        let l2 = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(devuelve: [1]))
        return try Cascada.armar(motor: m, l2: l2).decidir("x", pregunta)
    }

    func testL2cUsaTauL2cSiEsMayorOIgualACero() throws {
        XCTAssertTrue(try l2c(tauConj: 0.9).escalar) // 0.7 < 0.9: el servidor también escala
    }

    func testSinTauL2cL2UsaTauEscalate() throws {
        let r = try l2c(tauConj: -1)
        XCTAssertFalse(r.escalar)
        XCTAssertEqual(r.capa, "L2")
    }

    func testSinConjTauL2cNoSeAplica() throws {
        XCTAssertFalse(try l2c(tauConj: 0.9, conj: false).escalar)
    }

    // --- #14: errores de capa visibles y torre que falla no se recalcula ---

    func testUnErrorDeCapaSeRegistraConSuNombre() throws {
        let m = MotorFalso()
        m.l0 = { "esto no es json" }
        m.l1 = { json("soporte", 0.95, ["soporte": 0.95]) }
        var vistos: [String] = []
        let r = try Cascada.armar(motor: m, alErrorCapa: { capa, _ in vistos.append(capa) }).decidir("x", pregunta)
        XCTAssertEqual(r.capa, "L1")
        XCTAssertEqual(vistos, ["L0"])
    }

    func testUnaTorreQueFallaNoSeRecalculaEnCadaLlamadaHastaElTtl() throws {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = ["t1", "t2"]
        final class Falla: CodificadorTorre {
            var n = 0
            func torre(_ texto: String) throws -> [Float] { n += 1; throw ErrorChispa("no carga") }
        }
        let enc = Falla()
        var t = 0.0
        let c = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(), codificador: enc,
                       ahora: { Date(timeIntervalSince1970: t) })
        XCTAssertThrowsError(try c.decidir("x", preguntaNueva))
        XCTAssertEqual(enc.n, 1)
        for _ in 0..<3 { XCTAssertFalse(try c.decidir("x", preguntaNueva).opina) }
        XCTAssertEqual(enc.n, 1) // la negativa cacheada evita más pasadas de la torre
        t = 61
        XCTAssertThrowsError(try c.decidir("x", preguntaNueva))
        XCTAssertEqual(enc.n, 2)
    }

    func testSiElMotorRechazaLasTorresSeLanzaYSeCacheaLaNegativa() throws {
        let m = MotorFalso()
        m.torres = false; m.aceptaTorres = false; m.textosTorre = ["t1", "t2"]
        final class Cuenta: CodificadorTorre {
            var n = 0
            func torre(_ texto: String) throws -> [Float] { n += 1; return [1, 2] }
        }
        let enc = Cuenta()
        let c = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(), codificador: enc)
        XCTAssertThrowsError(try c.decidir("x", preguntaNueva))
        XCTAssertFalse(try c.decidir("x", preguntaNueva).opina)
        XCTAssertEqual(enc.n, 2) // solo la primera llamada codificó (2 textos)
    }
}
