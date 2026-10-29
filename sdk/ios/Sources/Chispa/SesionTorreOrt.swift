import Foundation
import OnnxRuntimeBindings

/// El ONNX de la torre (sección TORR) sobre ONNX Runtime con el EP de CoreML (si no lo admite, cae a la CPU).
/// `ORTSession` solo abre rutas: los bytes de `Motor.onnxTorre` se escriben una vez (nombre y tamaño) en el directorio
/// temporal. Entradas `input_ids` y `attention_mask` (int64, [1, n]); salida `h` (float32, [1, d]).
/// Las llamadas a `run` se serializan.
public final class SesionTorreOrt: SesionTorre {
    private let entorno: ORTEnv
    private let sesion: ORTSession
    private let cerrojo = NSLock()

    public init(onnx: Data, coreML: Bool = true) throws {
        let ruta = FileManager.default.temporaryDirectory.appendingPathComponent("chispa-torre-\(onnx.count).onnx")
        if (try? Data(contentsOf: ruta, options: .alwaysMapped).count) != onnx.count {
            try onnx.write(to: ruta, options: .atomic)
        }
        entorno = try ORTEnv(loggingLevel: .warning)
        let opciones = try ORTSessionOptions()
        if coreML {
            try opciones.appendCoreMLExecutionProvider(with: ORTCoreMLExecutionProviderOptions())
        }
        sesion = try ORTSession(env: entorno, modelPath: ruta.path, sessionOptions: opciones)
    }

    public func embeber(_ ids: [Int64]) throws -> [Float] {
        guard !ids.isEmpty else { throw ErrorChispa("torre: texto sin tokens") }
        let forma: [NSNumber] = [1, NSNumber(value: ids.count)]
        let mascara = [Int64](repeating: 1, count: ids.count)
        func tensor(_ v: [Int64]) throws -> ORTValue {
            let d = NSMutableData(data: v.withUnsafeBufferPointer { Data(buffer: $0) })
            return try ORTValue(tensorData: d, elementType: .int64, shape: forma)
        }
        let entradas = ["input_ids": try tensor(ids), "attention_mask": try tensor(mascara)]
        cerrojo.lock()
        defer { cerrojo.unlock() }
        let salidas = try sesion.run(withInputs: entradas, outputNames: ["h"], runOptions: nil)
        guard let h = salidas["h"] else { throw ErrorChispa("torre: el modelo no devolvió h") }
        let forma2 = try h.tensorTypeAndShapeInfo().shape.map { $0.intValue }
        guard forma2.count == 2, forma2[0] == 1 else { throw ErrorChispa("torre: forma de h \(forma2)") }
        let bytes = try h.tensorData() as Data
        let datos = bytes.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
        guard datos.count == forma2[1] else { throw ErrorChispa("torre: h trae \(datos.count) valores para \(forma2)") }
        return datos
    }
}
