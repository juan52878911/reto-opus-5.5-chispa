import XCTest
@testable import Chispa

/// El rechazo de las torres al vuelo dice por qué, y float16 se lee como float32.
final class TorreMotivoTests: XCTestCase {
    private let textos = ["passage: q · fraude · cargo", "passage: q · tarjeta · bloqueada"]

    private func capa(_ m: MotorFalso, _ enc: CodificadorTorre) -> CapaL2 {
        CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(devuelve: [0, 7, 2]), codificador: enc, ahora: { 0 })
    }

    func testElMensajeDeErrorIncluyeElMotivoDelMotor() throws {
        let m = MotorFalso()
        m.torres = false
        m.textosTorre = textos
        m.aceptaTorres = false
        m.motivoRechazo = "d=2 no casa con el Dim=256 que declara TORR"
        let enc = ZeroShotTests.Codificador()
        XCTAssertThrowsError(try capa(m, enc).decidir("hola", preguntaNueva)) { e in
            let msg = "\(e)"
            XCTAssertTrue(msg.contains("d=2, n=2"), msg)
            XCTAssertTrue(msg.contains("Dim=256"), msg)
        }
    }

    func testMedioAFloat32ValoresConocidos() {
        XCTAssertEqual(medioAFloat32(0x3C00), 1)
        XCTAssertEqual(medioAFloat32(0xC000), -2)
        XCTAssertEqual(medioAFloat32(0x3800), 0.5)
        XCTAssertEqual(medioAFloat32(0x7BFF), 65504)
        XCTAssertEqual(medioAFloat32(0x0001), Float(sign: .plus, exponent: -24, significand: 1))
        XCTAssertEqual(medioAFloat32(0x03FF), 1023 * Float(sign: .plus, exponent: -24, significand: 1))
        XCTAssertEqual(medioAFloat32(0x7C00), .infinity)
        XCTAssertEqual(medioAFloat32(0xFC00), -.infinity)
        XCTAssertTrue(medioAFloat32(0x7E00).isNaN)
    }

    func testLeerFloat32AceptaFloat32YFloat16() throws {
        var f32 = Data()
        for x: Float in [1, -2, 0.5] { var b = x.bitPattern.littleEndian; f32.append(Data(bytes: &b, count: 4)) }
        XCTAssertEqual(try leerFloat32(f32, esperados: 3, "torre"), [1, -2, 0.5])
        var f16 = Data()
        for x: UInt16 in [0x3C00, 0xC000, 0x3800] { var b = x.littleEndian; f16.append(Data(bytes: &b, count: 2)) }
        XCTAssertEqual(try leerFloat32(f16, esperados: 3, "torre"), [1, -2, 0.5])
        XCTAssertThrowsError(try leerFloat32(f16, esperados: 5, "torre"))
    }

    func testRespuestaVaciaDelMotorTieneMensajeClaro() {
        XCTAssertThrowsError(try SalidaCapa.desdeJson("")) { XCTAssertTrue("\($0)".contains("vacía")) }
    }
}
