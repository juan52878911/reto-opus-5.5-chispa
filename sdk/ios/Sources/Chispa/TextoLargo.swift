import Foundation

/// Qué hacer con un texto más largo que el truncado de L1 (`max_tokens` del modelo) y de L2 (`chispa.consulta.max_len`, 128 por
/// defecto). Mismo objeto que `texto_largo` de la config del servidor; el valor por defecto es `.cabeza`: los primeros tokens, lo
/// de siempre (bit a bit).
///
/// - `cabeza`: los primeros tokens.
/// - `cabeza_cola`: la mitad de los primeros y la mitad de los últimos.
/// - `trozos`: ventanas con `solape` tokens compartidos, como mucho `maxTrozos` (0 = 8, máximo 64); cada una se decide y se agregan
///   las probabilidades por opción con `agregacion` (`max` o `media`).
///
/// `ventanaL1` (0 = `max_tokens` del modelo) es la ventana de L1 con `cabeza_cola` y `trozos`; con `cabeza` no tiene efecto.
/// El motor Go valida los valores al abrir y lanza `ErrorChispa` si no valen.
public struct TextoLargo: Equatable {
    public var estrategia: String
    public var agregacion: String
    public var solape: Int
    public var maxTrozos: Int
    public var ventanaL1: Int

    public init(estrategia: String = "cabeza", agregacion: String = "media", solape: Int = 0, maxTrozos: Int = 0, ventanaL1: Int = 0) {
        self.estrategia = estrategia
        self.agregacion = agregacion
        self.solape = solape
        self.maxTrozos = maxTrozos
        self.ventanaL1 = ventanaL1
    }

    public static let cabeza = TextoLargo()

    func json() -> String {
        let o: [String: Any] = ["estrategia": estrategia, "agregacion": agregacion, "solape": solape,
                                "max_trozos": maxTrozos, "ventana_l1": ventanaL1]
        return String(decoding: try! JSONSerialization.data(withJSONObject: o, options: [.sortedKeys]), as: UTF8.self)
    }
}
