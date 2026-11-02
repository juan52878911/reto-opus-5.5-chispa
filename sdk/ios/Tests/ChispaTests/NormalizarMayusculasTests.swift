import XCTest
@testable import Chispa

/// Casos copiados de server/decide/testdata/normalizacion.json (entrada → salida de `normalizar_mayusculas` en Python).
final class NormalizarMayusculasTests: XCTestCase {
    private let casos: [(String, String)] = [
        ("ABCDEFG", "ABCDEFG"),
        ("ABCDEFGHIJklmn", "abcdefghijklmn"),
        ("ABCDEFGhij", "ABCDEFGhij"),
        ("ABCDEFGHij", "abcdefghij"),
        ("ÁRBOL ÑANDÚ ÉXITO", "árbol ñandú éxito"),
        ("12345 !!! 678", "12345 !!! 678"),
        ("", ""),
        ("HOLA 😀 QUIERO CANCELAR 123 MI TARJETA 💳", "hola 😀 quiero cancelar 123 mi tarjeta 💳"),
        ("Quiero cancelar mi tarjeta", "Quiero cancelar mi tarjeta"),
        ("ARBOL ñandú", "ARBOL ñandú"),
        ("CANCELAR MI TARJETA YA", "cancelar mi tarjeta ya"),
        ("¿QUÉ PASA CON MI PEDIDO? Gracias", "¿qué pasa con mi pedido? gracias"),
        ("LA CITA Nº 2ª vez", "LA CITA Nº 2ª vez"), // «ª» y «º» son letras, no mayúsculas
    ]

    func testParidadConPython() {
        for (entrada, salida) in casos { XCTAssertEqual(normalizarMayusculas(entrada), salida, entrada) }
    }

    func testLimites() {
        XCTAssertEqual(normalizarMayusculas("ABCDEFG"), "ABCDEFG") // 7 letras
        XCTAssertEqual(normalizarMayusculas("ABCDEFGH"), "abcdefgh") // 8 letras
        XCTAssertEqual(normalizarMayusculas("ABCDEFGHIJKLMNopqrst"), "ABCDEFGHIJKLMNopqrst") // 70 % exacto
        let setentaYUno = String(repeating: "A", count: 71) + String(repeating: "b", count: 29)
        XCTAssertEqual(normalizarMayusculas(setentaYUno), setentaYUno.lowercased() // ASCII: igual que el mapeo simple)
        let setenta = String(repeating: "A", count: 70) + String(repeating: "b", count: 30)
        XCTAssertEqual(normalizarMayusculas(setenta), setenta)
    }

    func testIdempotente() {
        for (entrada, _) in casos {
            let una = normalizarMayusculas(entrada)
            XCTAssertEqual(normalizarMayusculas(una), una)
        }
    }

    private final class TokenizadorQueApunta: Tokenizador {
        var vistos: [String] = []
        func ids(_ texto: String) throws -> [Int64] { vistos.append(texto); return [0, 7, 2] }
    }

    func testL2NormalizaElMensajeAntesDeTokenizar() throws {
        let m = MotorFalso()
        m.l2 = { json("compra", 0.9, ["compra": 0.9]) }
        let tok = TokenizadorQueApunta()
        let capa = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: tok)
        _ = try capa.decidir("CANCELAR MI TARJETA YA", pregunta)
        _ = try capa.decidir("cancelar mi tarjeta ya", pregunta)
        _ = try capa.decidir("ABCDEFG", pregunta)
        XCTAssertEqual(tok.vistos, ["cancelar mi tarjeta ya", "cancelar mi tarjeta ya", "ABCDEFG"])
    }
}
