import XCTest
@testable import Chispa

final class ModelosTests: XCTestCase {
    func testPreguntaAJsonComoElServidor() throws {
        let o = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(pregunta.json().utf8)) as? [String: Any])
        XCTAssertEqual(o["question"] as? String, "¿Qué quiere el cliente?")
        XCTAssertEqual(o["kind"] as? String, "choice")
        let ops = try XCTUnwrap(o["options"] as? [[String: String]])
        XCTAssertEqual(ops.count, 3)
        XCTAssertEqual(ops[0]["id"], "compra")
        XCTAssertEqual(ops[0]["description"], "quiere comprar")
        XCTAssertNil(ops[2]["description"]) // sin descripción no se envía el campo
    }

    func testParseaUnaRespuestaCompleta() throws {
        let s = try SalidaCapa.desdeJson(#"{"ok":true,"opina":true,"answer":"queja","conf":0.75,"probs":{"queja":0.75,"compra":0.25}}"#)
        XCTAssertTrue(s.opina)
        XCTAssertEqual(s.respuesta, "queja")
        XCTAssertEqual(s.confianza, 0.75, accuracy: 1e-12)
        XCTAssertEqual(s.probs["compra"] ?? -1, 0.25, accuracy: 1e-12)
    }

    func testSinOpinionYErrores() throws {
        XCTAssertFalse(try SalidaCapa.desdeJson(#"{"ok":true,"opina":false,"answer":"","conf":0,"probs":{}}"#).opina)
        XCTAssertThrowsError(try SalidaCapa.desdeJson(#"{"ok":false,"error":"el fichero no trae la sección L1"}"#)) {
            XCTAssertEqual(($0 as? ErrorChispa)?.mensaje, "el fichero no trae la sección L1")
        }
        XCTAssertThrowsError(try SalidaCapa.desdeJson("esto no es json")) {
            XCTAssertEqual(($0 as? ErrorChispa)?.mensaje, "respuesta de la capa ilegible")
        }
    }

    func testConfianzaCeroNoOpinaAunqueHayaRespuesta() {
        XCTAssertFalse(SalidaCapa(respuesta: "a", confianza: 0, probs: [:]).opina)
        XCTAssertFalse(SalidaCapa(respuesta: "", confianza: 0.9, probs: [:]).opina)
    }
}
