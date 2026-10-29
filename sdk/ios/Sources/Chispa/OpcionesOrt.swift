import Foundation
import OnnxRuntimeBindings

/// `ORTSessionOptions` con el `proveedor` (CoreML añade su EP; CPU no añade nada). Lanza si el EP no se puede añadir.
func opcionesOrt(_ proveedor: ProveedorOrt) throws -> ORTSessionOptions {
    let opciones = try ORTSessionOptions()
    if proveedor == .coreML {
        try opciones.appendCoreMLExecutionProvider(with: ORTCoreMLExecutionProviderOptions())
    }
    return opciones
}
