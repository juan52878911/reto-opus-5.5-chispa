import XCTest
@testable import Chispa

final class ConjTests: XCTestCase {
    let l0: [String: Double] = ["compra": 0.5, "soporte": 0.3, "saludo": 0.2]
    var previasL0: [String: SalidaCapa] { ["L0": SalidaCapa(respuesta: "compra", confianza: 0.5, probs: l0)] }

    func capa(_ m: MotorFalso) -> CapaL2 {
        let s = SesionFalsa()
        s.devuelve = Ranuras(datos: [1, -2, 0.5, 4], k: 2)
        return CapaL2(motor: m, sesion: s, tokenizador: TokenizadorFalso(devuelve: [0, 7, 2]))
    }

    func testConConjYProbabilidadesDeL0DecideLaCabezaConjunta() throws {
        let m = MotorFalso()
        m.conj = true
        m.cabeza = { json("soporte", 0.91, ["soporte": 0.91]) }
        let r = try capa(m).decidir("hola", pregunta, previas: previasL0)
        XCTAssertEqual(r.respuesta, "soporte")
        XCTAssertEqual(r.confianza, 0.91, accuracy: 1e-12)
        XCTAssertEqual(m.llamadas, ["CONJ"]) // no llega a puntuarL2
        let j = try JSONSerialization.jsonObject(with: Data(m.ultimoSimsJson!.utf8)) as! [String: Any]
        XCTAssertEqual(j["question"] as? String, pregunta.texto)
        XCTAssertEqual(j["k"] as? Int, 2)
        XCTAssertEqual((j["l0"] as? [String: Double])?["compra"], 0.5)
        XCTAssertEqual((j["ranuras"] as? [Double])?.map { Float($0) }, [1, -2, 0.5, 4])
    }

    func testSinConjUsaPuntuarL2() throws {
        let m = MotorFalso()
        m.l2 = { json("compra", 0.8, ["compra": 0.8]) }
        let r = try capa(m).decidir("hola", pregunta, previas: previasL0)
        XCTAssertEqual(r.respuesta, "compra")
        XCTAssertEqual(m.llamadas, ["L2"])
    }

    func testSinProbabilidadesDeL0UsaPuntuarL2() throws {
        let m = MotorFalso()
        m.conj = true
        m.l2 = { json("compra", 0.8, ["compra": 0.8]) }
        _ = try capa(m).decidir("hola", pregunta, previas: ["L0": .sinOpinion])
        _ = try capa(m).decidir("hola", pregunta)
        XCTAssertEqual(m.llamadas, ["L2", "L2"])
    }

    func testSiLaCabezaNoOpinaCaeAL2() throws {
        let m = MotorFalso()
        m.conj = true
        m.l2 = { json("compra", 0.8, ["compra": 0.8]) }
        let r = try capa(m).decidir("hola", pregunta, previas: previasL0)
        XCTAssertEqual(r.respuesta, "compra")
        XCTAssertEqual(m.llamadas, ["CONJ", "L2"])
    }

    func testLaCascadaPasaLasProbabilidadesDeL0AL2c() throws {
        let m = MotorFalso()
        m.conj = true
        m.l0 = { json("compra", 0.5, ["compra": 0.5, "soporte": 0.3, "saludo": 0.2]) }
        m.cabeza = { json("compra", 0.95, ["compra": 0.95]) }
        let r = try Cascada.armar(motor: m, l2: capa(m)).decidir("hola", pregunta)
        XCTAssertEqual(r.capa, "L2")
        XCTAssertFalse(r.escalar)
        XCTAssertEqual(m.llamadas, ["L0", "L1", "CONJ"])
        let j = try JSONSerialization.jsonObject(with: Data(m.ultimoSimsJson!.utf8)) as! [String: Any]
        XCTAssertEqual((j["l0"] as? [String: Double])?["soporte"], 0.3)
    }

    func testTokenizadorDelMotorLeeInt32LittleEndian() throws {
        let m = MotorFalso()
        m.idsE5 = Data([0, 0, 0, 0, 0x91, 0x3A, 0x03, 0, 2, 0, 0, 0]) // 0, 211601, 2
        XCTAssertEqual(try TokenizadorMotor(motor: m).ids("x"), [0, 211601, 2])
        XCTAssertTrue(m.tieneTokenizadorE5())
        XCTAssertThrowsError(try TokenizadorMotor(motor: MotorFalso()).ids("x")) { error in
            XCTAssertEqual(error as? ErrorChispa, ErrorChispa("el motor no tiene el tokenizador de e5"))
        }
    }
}
