import XCTest
@testable import Chispa

/// `escalate_reason` con los mismos valores que el servidor y la regla «score solo con ids 1..K».
final class EscalateReasonTests: XCTestCase {
    private func score(_ ids: [String]) -> Pregunta { Pregunta("Gravedad", opciones: ids.map { Opcion($0) }, tipo: "score") }
    private func cascada(_ m: MotorFalso) throws -> Cascada {
        try Cascada.armar(motor: m, l2: CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso()))
    }

    func testLosValoresSonLosDelServidor() {
        XCTAssertEqual(MotivoEscalada.sinOpinion, "sin_opinion")
        XCTAssertEqual(MotivoEscalada.bajaConfianza, "baja_confianza")
        XCTAssertEqual(MotivoEscalada.scoreIdsNoValidos, "score_ids_no_validos")
    }

    func testBajaConfianzaSiAlgunaOpinaPeroNoLlegaATau() throws {
        let m = MotorFalso()
        m.l1 = { json("compra", 0.6, ["compra": 0.6]) }
        let r = try cascada(m).decidir("x", pregunta)
        XCTAssertTrue(r.escalar)
        XCTAssertEqual(r.escalateReason, "baja_confianza")
    }

    func testSinOpinionSiNingunaOpina() throws {
        let r = try cascada(MotorFalso()).decidir("x", pregunta)
        XCTAssertTrue(r.escalar)
        XCTAssertEqual(r.escalateReason, "sin_opinion")
    }

    func testScoreConIdsFueraDe1aKNoOpinaYLoDice() throws {
        let casos = [["bajo", "medio", "alto"], ["0", "1", "2"], ["01", "2", "3"], ["+1", "2", "3"], ["1", "2", "4"], ["1", "1", "2"]]
        for ids in casos {
            let r = try cascada(MotorFalso()).decidir("x", score(ids))
            XCTAssertTrue(r.escalar, "\(ids)")
            XCTAssertEqual(r.escalateReason, "score_ids_no_validos", "\(ids)")
        }
    }

    func testScoreConIdsValidosEnCualquierOrdenNoEsScoreIdsNoValidos() throws {
        for ids in [["1", "2", "3"], ["3", "1", "2"], ["2", "3", "1"]] {
            XCTAssertTrue(score(ids).scoreIdsValidos)
            XCTAssertEqual(try cascada(MotorFalso()).decidir("x", score(ids)).escalateReason, "sin_opinion")
        }
    }

    func testScoreIdsValidosSoloMiraScore() {
        XCTAssertTrue(pregunta.scoreIdsValidos) // choice con ids cualesquiera
        XCTAssertFalse(score([]).scoreIdsValidos)
        XCTAssertFalse(score(["2"]).scoreIdsValidos)
    }

    func testSiUnaCapaFallaNoHayMotivo() throws {
        let m = MotorFalso()
        m.l0 = { "esto no es json" }
        let r = try cascada(m).decidir("x", pregunta)
        XCTAssertTrue(r.escalar)
        XCTAssertNil(r.escalateReason)
    }

    func testSiDecideUnaCapaNoHayMotivo() throws {
        let m = MotorFalso()
        m.l0 = { json("compra", 0.95, ["compra": 0.95]) }
        XCTAssertNil(try cascada(m).decidir("x", pregunta).escalateReason)
    }

    func testL2NoTokenizaNiLlamaAOnnxConIdsNoValidos() throws {
        let m = MotorFalso()
        let s = SesionFalsa()
        var tokenizo = false
        let capa = CapaL2(motor: m, sesion: s, tokenizador: TokenizadorFalso(alTokenizar: { tokenizo = true }))
        let r = try capa.decidir("x", score(["bajo", "medio", "alto"]))
        XCTAssertFalse(r.opina)
        XCTAssertFalse(tokenizo)
        XCTAssertEqual(s.llamadas, 0)
        XCTAssertFalse(m.llamadas.contains("L2"))
    }
}
