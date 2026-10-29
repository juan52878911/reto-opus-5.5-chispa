import XCTest
@testable import Chispa

/// El tipo `multi`: cada opción es un sí/no; la confianza de la capa es la de la opción más dudosa (la calcula el motor).
final class MultiTests: XCTestCase {
    private let probs = ["cobro": 0.93, "atencion": 0.81, "fraude": 0.07]

    private func cascada(_ m: MotorFalso) throws -> Cascada {
        try Cascada.armar(motor: m, l2: CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso()))
    }

    func testPreguntaMultiViajaConSuKind() throws {
        let o = try JSONSerialization.jsonObject(with: Data(preguntaMulti.json().utf8)) as! [String: Any]
        XCTAssertEqual(o["kind"] as? String, "multi")
    }

    func testLeeLasActivasYLasProbsPorOpcion() throws {
        let s = try SalidaCapa.desdeJson(jsonMulti(["cobro", "atencion"], 0.81, probs))
        XCTAssertTrue(s.opina)
        XCTAssertEqual(s.respuesta, "cobro")
        XCTAssertEqual(s.respuestas, ["cobro", "atencion"])
        XCTAssertEqual(s.probs["fraude"] ?? -1, 0.07, accuracy: 1e-12) // las p no suman 1
    }

    func testSinAnswersNoEsMulti() throws {
        XCTAssertNil(try SalidaCapa.desdeJson(json("compra", 0.9, ["compra": 0.9])).respuestas)
    }

    func testConActivasLaCapaQueLlegaATauResponde() throws {
        let m = MotorFalso()
        m.l1 = { jsonMulti(["cobro", "atencion"], 0.81, self.probs) }
        let r = try cascada(m).decidir("me cobraron dos veces y nadie contesta", preguntaMulti)
        XCTAssertFalse(r.escalar)
        XCTAssertEqual(r.capa, "L1")
        XCTAssertEqual(r.respuesta, "cobro")
        XCTAssertEqual(r.respuestas, ["cobro", "atencion"])
        XCTAssertEqual(r.confianza, 0.81, accuracy: 1e-12)
        XCTAssertEqual(m.llamadas, ["L0", "L1"]) // L0 no opina en multi, L1 basta
    }

    func testNingunaActivaEsUnaRespuestaValidaYNoEscala() throws {
        let m = MotorFalso()
        m.l1 = { jsonMulti([], 0.90, ["cobro": 0.05, "atencion": 0.10, "fraude": 0.02]) }
        let r = try cascada(m).decidir("hola, buenos días", preguntaMulti)
        XCTAssertFalse(r.escalar)
        XCTAssertEqual(r.capa, "L1")
        XCTAssertEqual(r.respuesta, "")
        XCTAssertTrue(r.respuestas.isEmpty)
        XCTAssertEqual(r.confianza, 0.90, accuracy: 1e-12)
    }

    func testUnaOpcionDudosaHaceQueLaCapaNoLleguePasaALaSiguiente() throws {
        // L1: una opción está en 0,55 → la confianza de la capa es 0,55 < τ y se pasa a L2
        let m = MotorFalso()
        m.l1 = { jsonMulti(["cobro"], 0.55, ["cobro": 0.95, "atencion": 0.45, "fraude": 0.03]) }
        m.l2 = { jsonMulti(["cobro", "atencion"], 0.88, ["cobro": 0.97, "atencion": 0.88, "fraude": 0.02]) }
        let r = try cascada(m).decidir("x", preguntaMulti)
        XCTAssertFalse(r.escalar)
        XCTAssertEqual(r.capa, "L2")
        XCTAssertEqual(r.respuestas, ["cobro", "atencion"])
        XCTAssertEqual(m.llamadas, ["L0", "L1", "L2"])
    }

    func testSiNingunaCapaLlegaEscalaConLasActivasDeLaMejorPista() throws {
        let m = MotorFalso()
        m.l1 = { jsonMulti(["cobro"], 0.55, ["cobro": 0.95, "atencion": 0.45, "fraude": 0.03]) }
        m.l2 = { jsonMulti(["cobro", "fraude"], 0.60, ["cobro": 0.90, "atencion": 0.20, "fraude": 0.60]) }
        let r = try cascada(m).decidir("x", preguntaMulti)
        XCTAssertTrue(r.escalar)
        XCTAssertEqual(r.capa, "escalar")
        XCTAssertEqual(r.confianza, 0.60, accuracy: 1e-12)
        XCTAssertEqual(r.respuestas, ["cobro", "fraude"]) // la pista es la de mayor confianza (L2)
    }

    func testEscalarSinNingunaOpinionDejaRespuestasVacias() throws {
        let r = try cascada(MotorFalso()).decidir("x", preguntaMulti)
        XCTAssertTrue(r.escalar)
        XCTAssertTrue(r.respuestas.isEmpty)
    }

    func testChoiceNoLlevaRespuestas() throws {
        let m = MotorFalso()
        m.l0 = { json("compra", 0.95, ["compra": 0.95]) }
        XCTAssertTrue(try cascada(m).decidir("x", pregunta).respuestas.isEmpty)
    }
}
