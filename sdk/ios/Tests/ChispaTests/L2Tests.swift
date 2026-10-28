import XCTest
@testable import Chispa

final class L2Tests: XCTestCase {
    func testSinTorresNoTokenizaNiLlamaAOnnx() throws {
        let m = MotorFalso()
        m.torres = false
        let s = SesionFalsa()
        var tokenizo = false
        let capa = CapaL2(motor: m, sesion: s, tokenizador: TokenizadorFalso(alTokenizar: { tokenizo = true }))
        XCTAssertFalse(try capa.decidir("hola", pregunta).opina)
        XCTAssertFalse(tokenizo)
        XCTAssertEqual(s.llamadas, 0)
        XCTAssertTrue(m.llamadas.isEmpty)
    }

    func testPasaLosIdsYLasRanurasEnFloat32LittleEndian() throws {
        let m = MotorFalso()
        m.l2 = { json("compra", 0.9, ["compra": 0.9]) }
        let s = SesionFalsa()
        s.devuelve = Ranuras(datos: [1, -2, 0.5, 4], k: 2)
        let r = try CapaL2(motor: m, sesion: s, tokenizador: TokenizadorFalso(devuelve: [0, 7, 2])).decidir("hola", pregunta)
        XCTAssertEqual(r.respuesta, "compra")
        XCTAssertEqual(s.ultimosIds, [0, 7, 2])
        XCTAssertEqual(m.ultimoK, 2)
        var esperado = Data()
        for x: Float in [1, -2, 0.5, 4] {
            var le = x.bitPattern.littleEndian
            withUnsafeBytes(of: &le) { esperado.append(contentsOf: $0) }
        }
        XCTAssertEqual(m.ultimasRanuras, esperado)
    }

    func testSinTokensNoOpina() throws {
        let s = SesionFalsa()
        let capa = CapaL2(motor: MotorFalso(), sesion: s, tokenizador: TokenizadorFalso(devuelve: []))
        XCTAssertFalse(try capa.decidir("", pregunta).opina)
        XCTAssertEqual(s.llamadas, 0)
    }

    func testMontarSoloCreaLaSesionConTokenizadorYConL2() throws {
        let s = SesionFalsa()
        var rutas = 0
        let sinTok = try Chispa.montar(motor: MotorFalso(), tokenizador: nil, onnx: { rutas += 1; return "x.onnx" }, crearSesion: { _ in s })
        XCTAssertEqual(rutas, 0)
        XCTAssertEqual(sinTok.capas, ["L0", "L1"])

        let m = MotorFalso()
        m.l2 = { json("compra", 0.95, ["compra": 0.95]) }
        let conTok = try Chispa.montar(motor: m, tokenizador: TokenizadorFalso(), onnx: { rutas += 1; return "x.onnx" }, crearSesion: { _ in s })
        XCTAssertEqual(rutas, 1)
        XCTAssertEqual(conTok.capas, ["L0", "L1", "L2"])
        let r = conTok.decidir("hola", [pregunta, pregunta])
        XCTAssertEqual(r.count, 2)
        XCTAssertEqual(r[0].capa, "L2")

        let sinL2 = MotorFalso()
        sinL2.presentes = ["L1"]
        rutas = 0
        _ = try Chispa.montar(motor: sinL2, tokenizador: TokenizadorFalso(), onnx: { rutas += 1; return "x" }, crearSesion: { _ in s })
        XCTAssertEqual(rutas, 0)
    }

    func testAlSoltarLaInstanciaSeCierraElMotor() throws {
        let m = MotorFalso()
        var c: Chispa? = try Chispa.montar(motor: m, tokenizador: nil, onnx: { "x" }, crearSesion: { _ in SesionFalsa() })
        XCTAssertFalse(m.cerrado)
        c = nil
        XCTAssertNil(c)
        XCTAssertTrue(m.cerrado)
    }
}
