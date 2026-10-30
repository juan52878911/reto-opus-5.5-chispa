import XCTest
@testable import Chispa

final class TextoLargoTests: XCTestCase {
    /// `[n][len][ids…]…` como lo da el motor.
    private func ventanas(_ v: [[Int32]]) -> Data {
        var d = Data()
        func put(_ x: Int32) { var le = x.littleEndian; withUnsafeBytes(of: &le) { d.append(contentsOf: $0) } }
        put(Int32(v.count))
        for w in v {
            put(Int32(w.count))
            for id in w { put(id) }
        }
        return d
    }

    func testTokenizadorMotorLeeLasVentanas() throws {
        let m = MotorFalso()
        m.trozos = ventanas([[0, 7, 2], [0, 8, 9, 2]])
        let v = try TokenizadorMotor(motor: m).trozos("texto largo")
        XCTAssertEqual(v, [[0, 7, 2], [0, 8, 9, 2]])
    }

    func testSinTrozosDelMotorCaeAlTokenizarDeSiempre() throws {
        let m = MotorFalso()
        m.idsE5 = Data([0, 0, 0, 0, 7, 0, 0, 0, 2, 0, 0, 0])
        XCTAssertEqual(try TokenizadorMotor(motor: m).trozos("hola"), [[0, 7, 2]])
    }

    func testRespuestaTruncadaDelMotorEsError() {
        let m = MotorFalso()
        m.trozos = ventanas([[0, 7, 2]]).prefix(9)
        XCTAssertThrowsError(try TokenizadorMotor(motor: m).trozos("x"))
    }

    func testConUnaVentanaEsLoDeSiempre() throws {
        let m = MotorFalso()
        m.l2 = { json("compra", 0.9, ["compra": 0.9]) }
        m.trozos = ventanas([[0, 7, 2]])
        let s = SesionFalsa()
        s.devuelve = Ranuras(datos: [1, -2, 0.5, 4], k: 2)
        let r = try CapaL2(motor: m, sesion: s, tokenizador: TokenizadorMotor(motor: m)).decidir("hola", pregunta)
        XCTAssertEqual(r.respuesta, "compra")
        XCTAssertEqual(m.llamadas, ["L2"]) // puntuarL2, no puntuarL2Trozos
        XCTAssertEqual(m.ultimoK, 2)
        XCTAssertEqual(s.llamadas, 1)
    }

    func testConVariasVentanasCorreOnnxEnCadaUnaYPuntuaLasConcatenadas() throws {
        let m = MotorFalso()
        m.l2 = { json("compra", 0.9, ["compra": 0.9]) }
        m.trozos = ventanas([[0, 7, 2], [0, 8, 2], [0, 9, 2]])
        let s = SesionFalsa()
        s.devuelve = Ranuras(datos: [1, 2, 3, 4], k: 2)
        let r = try CapaL2(motor: m, sesion: s, tokenizador: TokenizadorMotor(motor: m)).decidir("texto largo", pregunta)
        XCTAssertEqual(r.respuesta, "compra")
        XCTAssertEqual(s.llamadas, 3)
        XCTAssertEqual(m.llamadas, ["L2T"])
        XCTAssertEqual(m.ultimosKs, "[2,2,2]")
        XCTAssertEqual(m.ultimasRanuras?.count, 3 * 4 * 4)
    }

    func testConCabezaConjuntaYL0LaCabezaDecideCadaVentana() throws {
        let m = MotorFalso()
        m.conj = true
        m.cabeza = { json("compra", 0.9, ["compra": 0.9]) }
        m.trozos = ventanas([[0, 7, 2], [0, 8, 2]])
        let s = SesionFalsa()
        s.devuelve = Ranuras(datos: [1, 2], k: 1)
        let l0 = try SalidaCapa.desdeJson(json("compra", 0.5, ["compra": 0.5, "soporte": 0.5]))
        let r = try CapaL2(motor: m, sesion: s, tokenizador: TokenizadorMotor(motor: m)).decidir("texto largo", pregunta, previas: ["L0": l0])
        XCTAssertEqual(r.respuesta, "compra")
        XCTAssertEqual(m.llamadas, ["CONJ"])
        let o = try JSONSerialization.jsonObject(with: Data(m.ultimoSimsJson!.utf8)) as! [String: Any]
        XCTAssertEqual(o["ks"] as? [Int], [1, 1])
        XCTAssertEqual((o["ranuras"] as? [Double])?.count, 4)
    }

    func testElTextoLargoPorDefectoEsCabeza() throws {
        XCTAssertEqual(TextoLargo.cabeza, TextoLargo())
        let js = TextoLargo(estrategia: "trozos", agregacion: "max", solape: 16, maxTrozos: 4, ventanaL1: 64).json()
        let o = try JSONSerialization.jsonObject(with: Data(js.utf8)) as! [String: Any]
        XCTAssertEqual(o["estrategia"] as? String, "trozos")
        XCTAssertEqual(o["agregacion"] as? String, "max")
        XCTAssertEqual(o["solape"] as? Int, 16)
        XCTAssertEqual(o["max_trozos"] as? Int, 4)
        XCTAssertEqual(o["ventana_l1"] as? Int, 64)
    }
}
