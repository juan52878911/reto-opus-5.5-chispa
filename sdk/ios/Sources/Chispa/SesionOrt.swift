import Foundation
import OnnxRuntimeBindings

/// El ONNX int8 de L2 sobre ONNX Runtime con el EP de CoreML; si no se puede añadir o la sesión no se crea con él, se reabre en CPU
/// (`proveedorEfectivo` dice cuál quedó).
/// Entradas `input_ids` y `attention_mask` (int64, [1, n]); salida `S` (float32, [1, K, d]).
/// Las llamadas a `run` se serializan, como en el servidor.
public final class SesionOrt: SesionRanuras {
    private let entorno: ORTEnv
    private let sesion: ORTSession
    private let cerrojo = NSLock()

    /// El proveedor con el que quedó la sesión (`.cpu` si el pedido falló).
    public let proveedorEfectivo: ProveedorOrt

    public init(rutaOnnx: String, proveedor: ProveedorOrt = proveedorOrtPorDefecto) throws {
        let env = try ORTEnv(loggingLevel: .warning)
        entorno = env
        let (s, efectivo) = try abrirConRespaldo(proveedor, etiqueta: "L2") { p in
            try ORTSession(env: env, modelPath: rutaOnnx, sessionOptions: try opcionesOrt(p))
        }
        sesion = s
        proveedorEfectivo = efectivo
    }

    /// Compatibilidad con `coreML: Bool`.
    public convenience init(rutaOnnx: String, coreML: Bool) throws {
        try self.init(rutaOnnx: rutaOnnx, proveedor: coreML ? .coreML : .cpu)
    }

    public func ranuras(_ ids: [Int64]) throws -> Ranuras {
        guard !ids.isEmpty else { throw ErrorChispa("L2: mensaje sin tokens") }
        let forma: [NSNumber] = [1, NSNumber(value: ids.count)]
        let mascara = [Int64](repeating: 1, count: ids.count)
        func tensor(_ v: [Int64]) throws -> ORTValue {
            let d = NSMutableData(data: v.withUnsafeBufferPointer { Data(buffer: $0) })
            return try ORTValue(tensorData: d, elementType: .int64, shape: forma)
        }
        let entradas = ["input_ids": try tensor(ids), "attention_mask": try tensor(mascara)]
        cerrojo.lock()
        defer { cerrojo.unlock() }
        let salidas = try sesion.run(withInputs: entradas, outputNames: ["S"], runOptions: nil)
        guard let s = salidas["S"] else { throw ErrorChispa("L2: el modelo no devolvió S") }
        let forma3 = try s.tensorTypeAndShapeInfo().shape.map { $0.intValue }
        guard forma3.count == 3, forma3[0] == 1 else { throw ErrorChispa("L2: forma de S \(forma3)") }
        let bytes = try s.tensorData() as Data
        let datos = try leerFloat32(bytes, esperados: forma3[1] * forma3[2], "L2") // float32, o float16 si el ONNX se exportó sin keep_io_types
        return Ranuras(datos: datos, k: forma3[1])
    }
}
