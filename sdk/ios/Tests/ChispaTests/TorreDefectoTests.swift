import XCTest
@testable import Chispa

/// El CodificadorTorre por defecto (ids del motor + ONNX de TORR) con motor y sesión falsos; ORT no corre en estos tests.
final class TorreDefectoTests: XCTestCase {
    let textos = ["passage: q · fraude · cargo", "passage: q · tarjeta · bloqueada"]

    func ids(_ v: [Int32]) -> Data { v.withUnsafeBufferPointer { Data(buffer: $0) } } // little endian en Apple

    final class SesionTorreFalsa: SesionTorre {
        var pedidos: [[Int64]] = []
        func embeber(_ ids: [Int64]) throws -> [Float] {
            pedidos.append(ids)
            return [Float(ids.count), 1]
        }
    }

    func motor() -> MotorFalso {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = textos
        m.onnxDeTorre = Data([7, 7])
        m.idsE5 = ids([0, 5, 2])
        m.idsDePasaje = { t in t.contains("fraude") ? self.ids([0, 9, 8, 2]) : self.ids([0, 9, 2]) }
        m.l2 = { json("fraude", 0.9, ["fraude": 0.9]) }
        return m
    }

    func testCodificaConLosIdsDelMotorYElOnnxDeTorreAbiertoUnaSolaVez() throws {
        let m = motor()
        let s = SesionTorreFalsa()
        var abiertas = 0
        var onnxVisto: Data?
        let enc = CodificadorTorreMotor(motor: m) { d in abiertas += 1; onnxVisto = d; return s }
        XCTAssertEqual(abiertas, 0) // perezosa
        XCTAssertEqual(try enc.torre(textos[0]), [4, 1])
        XCTAssertEqual(try enc.torre(textos[1]), [3, 1])
        XCTAssertEqual(abiertas, 1)
        XCTAssertEqual(onnxVisto, Data([7, 7]))
        XCTAssertEqual(s.pedidos[0], [0, 9, 8, 2])
    }

    func testSinIdsOSinOnnxLanza() {
        let m = motor()
        m.idsDePasaje = { _ in nil }
        XCTAssertThrowsError(try CodificadorTorreMotor(motor: m) { _ in SesionTorreFalsa() }.torre("x"))
        let m2 = motor()
        m2.onnxDeTorre = nil
        XCTAssertThrowsError(try CodificadorTorreMotor(motor: m2) { _ in SesionTorreFalsa() }.torre("x"))
    }

    func testMontarSinCodificadorDeLaAppUsaTorrDelFichero() throws {
        let m = motor()
        let s = SesionTorreFalsa()
        let ch = try Chispa.montar(motor: m, tokenizador: TokenizadorFalso(devuelve: [0, 2]), onnx: { "x.onnx" },
                                   crearSesion: { _ in SesionFalsa() }, crearSesionTorre: { _ in s })
        let r = ch.decidir("hola", [preguntaNueva])[0]
        XCTAssertEqual(r.capa, "L2")
        XCTAssertEqual(m.nInstaladas, 2)
        XCTAssertEqual(s.pedidos.count, 2)
        let esperado = [Float(4), 1, 3, 1].withUnsafeBufferPointer { Data(buffer: $0) }
        XCTAssertEqual(m.torresInstaladas, esperado)
    }

    func testSinTorrNiCodificadorUnEsquemaNuevoNoOpina() throws {
        let m = motor()
        m.onnxDeTorre = nil
        let ch = try Chispa.montar(motor: m, tokenizador: TokenizadorFalso(devuelve: [0, 2]), onnx: { "x.onnx" },
                                   crearSesion: { _ in SesionFalsa() })
        let r = ch.decidir("hola", [preguntaNueva])[0]
        XCTAssertTrue(r.escalar)
        XCTAssertEqual(r.capa, "escalar")
        XCTAssertFalse(m.llamadas.contains("L2"))
        XCTAssertFalse(m.llamadas.contains("TORRES"))
        XCTAssertEqual(m.nInstaladas, 0)
    }

    func testElCodificadorDeLaAppManda() throws {
        let m = motor()
        let s = SesionTorreFalsa()
        final class Fijo: CodificadorTorre { func torre(_ t: String) throws -> [Float] { [1, 1] } }
        let ch = try Chispa.montar(motor: m, tokenizador: TokenizadorFalso(devuelve: [0, 2]), onnx: { "x.onnx" },
                                   crearSesion: { _ in SesionFalsa() }, codificadorTorres: Fijo(),
                                   crearSesionTorre: { _ in s })
        _ = ch.decidir("hola", [preguntaNueva])
        XCTAssertTrue(s.pedidos.isEmpty)
    }
}
