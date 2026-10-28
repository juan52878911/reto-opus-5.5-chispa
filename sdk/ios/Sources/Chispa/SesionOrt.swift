import Foundation
import OnnxRuntimeBindings

/// El ONNX int8 de L2 sobre ONNX Runtime con el EP de CoreML (si el dispositivo no lo admite, ORT cae a la CPU).
/// Entradas `input_ids` y `attention_mask` (int64, [1, n]); salida `S` (float32, [1, K, d]).
/// Las llamadas a `run` se serializan, como en el servidor.
public final class SesionOrt: SesionRanuras {
    private let entorno: ORTEnv
    private let sesion: ORTSession
    private let cerrojo = NSLock()

    public init(rutaOnnx: String, coreML: Bool = true) throws {
        entorno = try ORTEnv(loggingLevel: .warning)
        let opciones = try ORTSessionOptions()
        if coreML {
            try opciones.appendCoreMLExecutionProvider(with: ORTCoreMLExecutionProviderOptions())
        }
        sesion = try ORTSession(env: entorno, modelPath: rutaOnnx, sessionOptions: opciones)
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
        let datos = bytes.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
        guard datos.count == forma3[1] * forma3[2] else { throw ErrorChispa("L2: S trae \(datos.count) valores para \(forma3)") }
        return Ranuras(datos: datos, k: forma3[1])
    }
}
