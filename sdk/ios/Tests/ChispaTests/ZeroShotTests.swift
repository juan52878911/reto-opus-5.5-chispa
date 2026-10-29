import XCTest
@testable import Chispa

/// Zero-shot (esquema que el .chispa no trae), few-shot (esquema entrenado dentro del .chispa) y L0TF.
final class ZeroShotTests: XCTestCase {
    let textos = ["passage: q · fraude · cargo", "passage: q · tarjeta · bloqueada"]

    final class Codificador: CodificadorTorre {
        var pedidos: [String] = []
        var falla = false
        var dims: (Int, Int)? // dimensión de la torre de fraude y la de tarjeta, para provocar un error
        func torre(_ texto: String) throws -> [Float] {
            pedidos.append(texto)
            if falla { throw ErrorChispa("sin memoria") }
            let fraude = texto.contains("fraude")
            if let d = dims { return [Float](repeating: 1, count: fraude ? d.0 : d.1) }
            return fraude ? [1, -2] : [0.5, 4]
        }
    }

    func capa(_ m: MotorFalso, _ enc: CodificadorTorre?, ahora: @escaping () -> UInt64 = { 0 }) -> CapaL2 {
        CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(devuelve: [0, 7, 2]), codificador: enc, ahora: ahora)
    }

    func testEsquemaNuevoLaPrimeraVezCalculaLasTorresYLaSegundaUsaLaCache() throws {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = textos
        m.l2 = { json("fraude", 0.9, ["fraude": 0.9]) }
        let enc = Codificador()
        let c = capa(m, enc)

        let r1 = try c.decidir("no reconozco un cargo", preguntaNueva)
        XCTAssertEqual(r1.respuesta, "fraude")
        XCTAssertEqual(enc.pedidos, textos)
        XCTAssertEqual(m.llamadas, ["TORRES", "L2"])
        XCTAssertEqual(m.nInstaladas, 2)
        var esperado = Data()
        for x: Float in [1, -2, 0.5, 4] {
            var le = x.bitPattern.littleEndian
            withUnsafeBytes(of: &le) { esperado.append(contentsOf: $0) }
        }
        XCTAssertEqual(m.torresInstaladas, esperado)

        let r2 = try c.decidir("otro mensaje", preguntaNueva)
        XCTAssertEqual(r2.respuesta, "fraude")
        XCTAssertEqual(enc.pedidos, textos) // no volvió a codificar
        XCTAssertEqual(m.llamadas, ["TORRES", "L2", "L2"])
        XCTAssertEqual(m.nInstaladas, 2)
    }

    func testSinCodificadorUnEsquemaNuevoNoOpinaYNoTokeniza() throws {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = textos
        var tokenizo = false
        let c = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(alTokenizar: { tokenizo = true }))
        XCTAssertFalse(try c.decidir("hola", preguntaNueva).opina)
        XCTAssertFalse(tokenizo)
        XCTAssertTrue(m.llamadas.isEmpty)
    }

    func testSiElMotorNoPideTextosNoOpina() throws {
        let m = MotorFalso()
        m.torres = false // motor sin soporte de torres al vuelo
        let enc = Codificador()
        XCTAssertFalse(try capa(m, enc).decidir("hola", preguntaNueva).opina)
        XCTAssertTrue(enc.pedidos.isEmpty)
    }

    func testSiElCodificadorFallaNoSeCacheaYSeReintentaPasadoElTtl() throws {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = textos
        m.l2 = { json("fraude", 0.9, ["fraude": 0.9]) }
        let enc = Codificador()
        enc.falla = true
        var t: UInt64 = 0
        let c = capa(m, enc, ahora: { t })
        XCTAssertThrowsError(try c.decidir("hola", preguntaNueva))
        XCTAssertEqual(m.nInstaladas, 0)
        enc.falla = false
        t = 61 * 1_000_000_000 // pasado el TTL de la caché negativa
        XCTAssertEqual(try c.decidir("hola", preguntaNueva).respuesta, "fraude")
    }

    func testDimensionesDeTorreDistintasSeRechazan() throws {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = textos
        let enc = Codificador()
        enc.dims = (1, 2)
        XCTAssertThrowsError(try capa(m, enc).decidir("hola", preguntaNueva))
        XCTAssertEqual(m.nInstaladas, 0)
    }

    func testCascadaZeroShotL1DudaYL2AlVueloDecide() throws {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = textos
        m.l1 = { json("fraude", 0.55, ["fraude": 0.55, "tarjeta": 0.45]) } // L1-zs con descripciones: por debajo de τ
        m.l2 = { json("fraude", 0.93, ["fraude": 0.93]) }
        let r = try Cascada.armar(motor: m, l2: capa(m, Codificador())).decidir("no reconozco un cargo", preguntaNueva)
        XCTAssertEqual(r.capa, "L2")
        XCTAssertFalse(r.escalar)
        XCTAssertEqual(m.llamadas, ["L0", "L1", "TORRES", "L2"])
    }

    func testCascadaZeroShotL1SeguraNoLlegaAL2() throws {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = textos
        m.l1 = { json("fraude", 0.9, ["fraude": 0.9]) }
        let enc = Codificador()
        let r = try Cascada.armar(motor: m, l2: capa(m, enc)).decidir("cargo raro", preguntaNueva)
        XCTAssertEqual(r.capa, "L1")
        XCTAssertTrue(enc.pedidos.isEmpty) // no se calcula ninguna torre si L1 basta
    }

    func testMontarPasaElCodificadorALaCapaL2() throws {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = textos
        m.l2 = { json("fraude", 0.95, ["fraude": 0.95]) }
        let ch = try Chispa.montar(motor: m, tokenizador: TokenizadorFalso(devuelve: [0, 2]), onnx: { "x.onnx" },
                                   crearSesion: { _ in SesionFalsa() }, codificadorTorres: Codificador())
        let r = ch.decidir("hola", [preguntaNueva])[0]
        XCTAssertEqual(r.capa, "L2")
        XCTAssertEqual(m.nInstaladas, 2)
    }

    func testFewShotElEsquemaEntrenadoVieneEnElFicheroYNoCalculaTorres() throws {
        // few-shot: chispa train metió L0 (L0TF) y ESQUEMAS del esquema; el SDK no necesita codificador
        let m = MotorFalso()
        m.l0 = { json("compra", 0.97, ["compra": 0.97, "soporte": 0.02, "saludo": 0.01]) }
        let enc = Codificador()
        let r = try Cascada.armar(motor: m, l2: capa(m, enc)).decidir("quiero dos camisetas", pregunta)
        XCTAssertEqual(r.capa, "L0")
        XCTAssertEqual(r.confianza, 0.97, accuracy: 1e-12)
        XCTAssertEqual(m.llamadas, ["L0"])
        XCTAssertTrue(enc.pedidos.isEmpty)
    }

    func testFewShotConTorresEnElFicheroL2NoCalculaNada() throws {
        let m = MotorFalso()
        m.textosTorre = textos
        m.l0 = { json("compra", 0.4, ["compra": 0.4, "soporte": 0.3, "saludo": 0.3]) }
        m.l1 = { json("compra", 0.5, ["compra": 0.5]) }
        m.l2 = { json("compra", 0.9, ["compra": 0.9]) }
        let enc = Codificador()
        XCTAssertEqual(try Cascada.armar(motor: m, l2: capa(m, enc)).decidir("hola", pregunta).capa, "L2")
        XCTAssertTrue(enc.pedidos.isEmpty)
        XCTAssertEqual(m.nInstaladas, 0)
    }

    func testL0TfPasaSusProbabilidadesALaCabezaConjuntaDeL2c() throws {
        // L0TF responde con sus probabilidades (por debajo de τ); L2c las recibe como «l0»
        let m = MotorFalso()
        m.conj = true
        m.l0 = { json("compra", 0.6, ["compra": 0.6, "soporte": 0.3, "saludo": 0.1]) }
        m.cabeza = { json("compra", 0.95, ["compra": 0.95]) }
        let r = try Cascada.armar(motor: m, l2: capa(m, nil)).decidir("hola", pregunta)
        XCTAssertEqual(r.capa, "L2")
        XCTAssertEqual(m.llamadas, ["L0", "L1", "CONJ"])
        let j = try JSONSerialization.jsonObject(with: Data(m.ultimoSimsJson!.utf8)) as! [String: Any]
        XCTAssertEqual((j["l0"] as? [String: Double])?["saludo"], 0.1)
    }
}
