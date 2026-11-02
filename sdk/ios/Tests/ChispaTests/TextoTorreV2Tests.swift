import XCTest
@testable import Chispa

/// Texto de torre v2 (META.texto_torre = «v2_sin_id»): lo construye el motor (chispamovil, con la regla de runtime/torre) y el SDK
/// lo pasa tal cual al codificador. Con descripción no lleva el id; sin ella, el texto v1.
final class TextoTorreV2Tests: XCTestCase {
    let v2 = ["passage: ¿Qué tipo de incidencia es? · cargo no reconocido", "passage: ¿Qué tipo de incidencia es? · tarjeta bloqueada o perdida"]

    final class Codificador: CodificadorTorre {
        var pedidos: [String] = []
        func torre(_ texto: String) throws -> [Float] {
            pedidos.append(texto)
            return texto.contains("cargo") ? [1, -2] : [0.5, 4]
        }
    }

    func testElCodificadorRecibeLosTextosDelMotorSinReconstruirlos() throws {
        let m = MotorFalso()
        m.torres = false
        m.versionTorre = "v2_sin_id"
        m.textosTorre = v2
        m.l2 = { json("fraude", 0.9, ["fraude": 0.9]) }
        let enc = Codificador()
        let c = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(devuelve: [0, 7, 2]), codificador: enc, ahora: { 0 })
        _ = try c.decidir("no reconozco un cargo", preguntaNueva)
        XCTAssertEqual(enc.pedidos, v2)
        XCTAssertEqual(m.textoTorre(), "v2_sin_id")
    }

    // Un motor degradado de verdad devuelve vacío en textosTorreL2; el falso sigue dando textos para comprobar que el SDK no los usa.
    func testMotorDegradadoNoCalculaTorresConElCodificadorDeLaApp() {
        let m = MotorFalso()
        m.torres = false
        m.motivoTorre = "texto_torre_inconsistente"
        m.textosTorre = v2
        m.l2 = { json("fraude", 0.9, ["fraude": 0.9]) }
        let enc = Codificador()
        let c = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(devuelve: [0, 7, 2]), codificador: enc, ahora: { 0 })
        _ = try? c.decidir("no reconozco un cargo", preguntaNueva)
        XCTAssertEqual(enc.pedidos, [])
        XCTAssertFalse(m.llamadas.contains("TORRES"))
    }

    func testElMotorExponeMotivoYAvisos() {
        let m = MotorFalso()
        XCTAssertEqual(m.torreAlVueloMotivo(), "")
        m.motivoTorre = "texto_torre_inconsistente"
        m.avisosApertura = "AVISO: torre al vuelo desactivada"
        XCTAssertEqual(m.torreAlVueloMotivo(), "texto_torre_inconsistente")
        XCTAssertEqual(m.avisos(), "AVISO: torre al vuelo desactivada")
    }

    func testSinElCampoLaVersionEsV1() {
        XCTAssertEqual(MotorFalso().textoTorre(), "v1")
    }
}
