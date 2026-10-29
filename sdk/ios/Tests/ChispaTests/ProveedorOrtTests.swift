import XCTest
@testable import Chispa

/// La elección de proveedor de ORT y su respaldo a CPU, con «sesiones» falsas; ORT no corre en estos tests.
final class ProveedorOrtTests: XCTestCase {
    struct Roto: Error {}

    func testCoreMLPorDefecto() {
        XCTAssertEqual(proveedorOrtPorDefecto, .coreML)
    }

    func testLaOpcionLlegaALaSesion() throws {
        for p in [ProveedorOrt.cpu, .coreML] {
            var pedidos: [ProveedorOrt] = []
            let (s, usado) = try abrirConRespaldo(p, etiqueta: "L2", aviso: { _ in XCTFail("no debía avisar") }) { (prov: ProveedorOrt) -> String in
                pedidos.append(prov)
                return "sesion-\(prov.rawValue)"
            }
            XCTAssertEqual(pedidos, [p])
            XCTAssertEqual(usado, p)
            XCTAssertEqual(s, "sesion-\(p.rawValue)")
        }
    }

    func testSiFallaCoreMLCaeACpuYAvisa() throws {
        var pedidos: [ProveedorOrt] = []
        var avisos: [String] = []
        let (s, usado) = try abrirConRespaldo(.coreML, etiqueta: "torre", aviso: { avisos.append($0) }) { (prov: ProveedorOrt) -> String in
            pedidos.append(prov)
            if prov != .cpu { throw Roto() }
            return "cpu"
        }
        XCTAssertEqual(pedidos, [.coreML, .cpu])
        XCTAssertEqual(usado, .cpu)
        XCTAssertEqual(s, "cpu")
        XCTAssertEqual(avisos.count, 1)
        XCTAssertTrue(avisos[0].contains("torre") && avisos[0].contains("CoreML"))
    }

    func testCpuNoReintentaYSiFallaSube() {
        var llamadas = 0
        XCTAssertThrowsError(try abrirConRespaldo(.cpu, etiqueta: "L2", aviso: { _ in XCTFail("no debía avisar") }) { (_: ProveedorOrt) -> String in
            llamadas += 1
            throw Roto()
        })
        XCTAssertEqual(llamadas, 1)
    }

    func testSiCpuTambienFallaSubeElError() {
        var llamadas = 0
        XCTAssertThrowsError(try abrirConRespaldo(.coreML, etiqueta: "L2", aviso: { _ in }) { (_: ProveedorOrt) -> String in
            llamadas += 1
            throw Roto()
        })
        XCTAssertEqual(llamadas, 2)
    }
}
