import Foundation

/// Lo que el SDK necesita del motor nativo (gomobile). Es un protocolo para poder probar la cascada con un motor
/// falso; `MotorNativo` es la implementación real.
public protocol Motor: AnyObject {
    /// Capas presentes en el fichero, p. ej. ["L0","L1","L2"].
    func capas() -> [String]
    func tieneCalib() -> Bool
    func tauEscalate() -> Double
    /// `tau_escalate_l2` de CALIB si existe; si no, `tauEscalate()` (ficheros anteriores). Es el τ de L2.
    func tauEscalateL2() -> Double
    /// `tau_l2c` de CALIB (el τ de L2 con CONJ, como en el servidor), o −1 si falta.
    func tauL2c() -> Double
    /// τ efectivo de L2 cuando sus torres salen al vuelo: el de CALIB o, si falta, 0,846 (lo decide el motor Go); −1 = sin τ propio.
    func tauL2EsquemaNuevo() -> Double
    /// sha256 hex de la sección de `tipo` (ver `seccionL2`, `seccionTorr`), o "" si el motor no lo sabe o no la hay.
    func hashSeccion(_ tipo: Int) -> String
    func decidirL0(_ texto: String, _ preguntaJson: String) -> String
    func decidirL1(_ texto: String, _ preguntaJson: String) -> String
    func torresL2(_ preguntaJson: String) -> Bool
    /// `ranuras`: K×d float32 little endian.
    func puntuarL2(_ preguntaJson: String, ranuras: Data, k: Int) -> String
    func extraerL2(a destino: String) throws
    func cerrar()

    /// El fichero trae CONJ (la cabeza conjunta, L2c).
    func tieneConj() -> Bool
    /// L2c: `simsJson` es la pregunta más `l0` (probabilidades de L0), `ranuras` (K×d aplanado) y `k`. Devuelve la
    /// misma forma que las demás capas; sin opinión si no hay cabeza para la pregunta.
    func cabezaConjunta(_ simsJson: String) -> String
    func tieneTokenizadorE5() -> Bool
    func cargarTokenizadorE5(ruta: String) throws
    /// Ids de e5 como int32 little endian (4 bytes por id), o nil si no se cargó el tokenizador.
    func tokenizarE5(_ texto: String) -> Data?
    /// Las ventanas de la consulta de e5 según `texto_largo` (`TextoLargo`): int32 little endian `[n][len₁][ids₁…][len₂][ids₂…]…`, cada
    /// ventana con sus `<s>` y `</s>`. Con `cabeza` (o un texto que cabe) es una sola, igual que `tokenizarE5`. nil si no hay
    /// tokenizador o el motor no sabe trocear (entonces vale `tokenizarE5`).
    func trozosE5(_ texto: String) -> Data?
    /// Como `puntuarL2` para varias ventanas de `trozosE5`: `ranuras` son las de cada ventana una tras otra (float32 little endian) y
    /// `ksJson` el número de filas de cada una (`[k1,k2,…]`). El motor agrega las probabilidades como dice `texto_largo`.
    func puntuarL2Trozos(_ preguntaJson: String, ranuras: Data, ksJson: String) -> String

    /// Zero-shot de L2 (esquema que el `.chispa` no trae en ESQUEMAS): textos de pasaje («passage: pregunta · opción ·
    /// descripción») cuyas torres hay que calcular, en el orden en que las espera `instalarTorresL2`; vacío si el
    /// motor no sabe pedirlas (motor sin soporte, o ya las tiene). Las torres que calcule el propio motor no pasan
    /// por aquí: basta con que `torresL2` diga true.
    func textosTorreL2(_ preguntaJson: String) -> [String]
    /// Versión del texto de torre del `.chispa` (META.texto_torre): «v1» (campo ausente) o «v2_sin_id». El motor (`chispamovil`)
    /// es el único que construye los textos de `textosTorreL2`; el SDK los pasa tal cual al codificador, sin reconstruirlos.
    func textoTorre() -> String
    /// Entrega al motor las torres de `preguntaJson` (`n` vectores de d float32 little endian, uno por texto de
    /// `textosTorreL2`); el motor las cuantiza y las cachea, así que la siguiente `torresL2` de ese esquema da true sin
    /// volver a calcular. false si no las acepta.
    func instalarTorresL2(_ preguntaJson: String, torres: Data, n: Int) -> Bool

    /// El fichero trae TORR (el ONNX de la torre de opción, para esquemas nuevos).
    func tieneTorre() -> Bool
    /// Bytes del ONNX de TORR (entradas `input_ids`/`attention_mask` int64, salida `h` (B,256) float32), o nil sin TORR.
    func onnxTorre() -> Data?
    /// Ids de e5 de un texto de torre (prefijo «passage: », recorte de TORR) como int32 little endian, o nil.
    func idsPasaje(_ texto: String) -> Data?
}

/// Tipos de sección de `format/chispa3` que se piden a `Motor.hashSeccion`.
let seccionL2 = 4
let seccionTorr = 9

public extension Motor {
    func tauEscalateL2() -> Double { tauEscalate() }
    func tauL2c() -> Double { -1 }
    func tauL2EsquemaNuevo() -> Double { -1 }
    func hashSeccion(_ tipo: Int) -> String { "" }
    func tieneConj() -> Bool { false }
    func cabezaConjunta(_ simsJson: String) -> String { #"{"ok":false,"error":"sin CONJ","probs":{}}"# }
    func cargarTokenizadorE5(ruta: String) throws { throw ErrorChispa("el motor no tiene tokenizador de e5") }
    func tieneTokenizadorE5() -> Bool { false }
    func tokenizarE5(_ texto: String) -> Data? { nil }
    func trozosE5(_ texto: String) -> Data? { nil }
    func puntuarL2Trozos(_ preguntaJson: String, ranuras: Data, ksJson: String) -> String {
        #"{"ok":false,"error":"el motor no puntúa trozos","probs":{}}"#
    }
    func textosTorreL2(_ preguntaJson: String) -> [String] { [] }
    func textoTorre() -> String { "v1" }
    func instalarTorresL2(_ preguntaJson: String, torres: Data, n: Int) -> Bool { false }
    func tieneTorre() -> Bool { false }
    func onnxTorre() -> Data? { nil }
    func idsPasaje(_ texto: String) -> Data? { nil }
}

/// Una capa de la cascada. Devuelve `.sinOpinion` si no tiene nada que decir; lanza si falla.
public protocol Capa {
    var nombre: String { get }
    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa
    /// Como `decidir`, con lo que dijeron las capas anteriores por nombre (L2c lee las probabilidades de L0).
    func decidir(_ texto: String, _ pregunta: Pregunta, previas: [String: SalidaCapa]) throws -> SalidaCapa
}

extension Capa {
    func decidir(_ texto: String, _ pregunta: Pregunta, previas: [String: SalidaCapa]) throws -> SalidaCapa {
        try decidir(texto, pregunta)
    }
}

struct CapaL0: Capa {
    let motor: Motor
    var nombre: String { "L0" }
    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa {
        try SalidaCapa.desdeJson(motor.decidirL0(texto, pregunta.json()))
    }
}

struct CapaL1: Capa {
    let motor: Motor
    var nombre: String { "L1" }
    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa {
        try SalidaCapa.desdeJson(motor.decidirL1(texto, pregunta.json()))
    }
}

/// Convierte un texto en los ids del tokenizador de e5 (con «query: » delante, tokens especiales y recorte al `max_len` del modelo, 128 por defecto; lo recorta el motor y la app no recorta por su cuenta).
public protocol Tokenizador {
    func ids(_ texto: String) throws -> [Int64]
}

/// El codificador de torres de opción (e5 de pasaje + cabeza de torre, un segundo ONNX): texto de pasaje → d floats.
/// Solo hace falta para esquemas nuevos cuando el motor no calcula las torres por su cuenta.
public protocol CodificadorTorre {
    func torre(_ texto: String) throws -> [Float]
}

/// El ONNX de la torre: ids (un texto de pasaje) → h (d floats).
public protocol SesionTorre: AnyObject {
    func embeber(_ ids: [Int64]) throws -> [Float]
}

/// El `CodificadorTorre` por defecto cuando el `.chispa` trae TORR: ids de `Motor.idsPasaje` y el ONNX de
/// `Motor.onnxTorre` sobre ONNX Runtime. La sesión (pesada) se abre la primera vez que hace falta una torre.
final class CodificadorTorreMotor: CodificadorTorre {
    private let motor: Motor
    private let crearSesion: (Data) throws -> SesionTorre
    private var sesion: SesionTorre?
    private let cerrojo = NSLock()

    init(motor: Motor, crearSesion: @escaping (Data) throws -> SesionTorre) {
        self.motor = motor
        self.crearSesion = crearSesion
    }

    func torre(_ texto: String) throws -> [Float] {
        guard let d = motor.idsPasaje(texto), !d.isEmpty else {
            throw ErrorChispa("torre: el motor no tiene tokenizador de e5 o TORR, o el texto no tiene tokens")
        }
        let ids: [Int64] = stride(from: 0, to: d.count - 3, by: 4).map { i in
            let v = UInt32(d[d.startIndex + i]) | UInt32(d[d.startIndex + i + 1]) << 8
                | UInt32(d[d.startIndex + i + 2]) << 16 | UInt32(d[d.startIndex + i + 3]) << 24
            return Int64(Int32(bitPattern: v))
        }
        cerrojo.lock()
        defer { cerrojo.unlock() }
        if sesion == nil {
            guard let onnx = motor.onnxTorre() else { throw ErrorChispa("el fichero no trae TORR") }
            sesion = try crearSesion(onnx)
        }
        return try sesion!.embeber(ids)
    }
}

/// Normalización de mayúsculas (docs/contrato-normalizacion.md): con al menos 8 letras y más del 70 % en mayúscula devuelve el
/// texto en minúsculas; si no, el mismo. Solo para el mensaje que entra a L2. Cuenta escalares Unicode (`isAlphabetic` y
/// `isUppercase` de `properties`, no los de `Character`, que da por mayúsculas «ª», «º») y pasa a minúsculas escalar a escalar con `properties.lowercaseMapping`,
/// quedándose con el primer escalar (mapeo simple, como Go: «İ» → «i», sigma final → «σ»; `lowercased()` daría «ς»).
public func normalizarMayusculas(_ texto: String) -> String {
    var letras = 0
    var mayus = 0
    for u in texto.unicodeScalars where u.properties.isAlphabetic {
        letras += 1
        if u.properties.isUppercase { mayus += 1 }
    }
    guard letras >= 8 && mayus * 10 > 7 * letras else { return texto }
    var salida = String.UnicodeScalarView()
    for u in texto.unicodeScalars {
        salida.append(u.properties.lowercaseMapping.unicodeScalars.first ?? u)
    }
    return String(salida)
}

/// Un `Tokenizador` que sabe dar varias ventanas de un texto largo (`texto_largo`); `CapaL2` lo usa si el tokenizador lo implementa.
public protocol TokenizadorTrozos: Tokenizador {
    /// Los ids de cada ventana; una sola (igual que `ids`) con `cabeza` o un texto que cabe.
    func trozos(_ texto: String) throws -> [[Int64]]
}

/// El tokenizador de e5 del propio motor (runtime/tok en Go): no hace falta que la app aporte uno.
struct TokenizadorMotor: TokenizadorTrozos {
    let motor: Motor

    func trozos(_ texto: String) throws -> [[Int64]] {
        guard let d = motor.trozosE5(texto) else { return [try ids(texto)] }
        let b = [UInt8](d)
        func entero(_ i: Int) -> Int? {
            guard i >= 0, i + 4 <= b.count else { return nil }
            let lo = UInt32(b[i]) | UInt32(b[i + 1]) << 8
            let hi = UInt32(b[i + 2]) << 16 | UInt32(b[i + 3]) << 24
            return Int(Int32(bitPattern: lo | hi))
        }
        guard let n = entero(0), n >= 0 else { throw ErrorChispa("trozosE5: respuesta truncada") }
        var pos = 4
        var out: [[Int64]] = []
        for _ in 0..<n {
            guard let len = entero(pos), len >= 0, pos + 4 + 4 * len <= b.count else { throw ErrorChispa("trozosE5: respuesta truncada") }
            pos += 4
            let base = pos
            out.append((0..<len).map { Int64(entero(base + 4 * $0)!) })
            pos += 4 * len
        }
        return out
    }

    func ids(_ texto: String) throws -> [Int64] {
        guard let d = motor.tokenizarE5(texto) else { throw ErrorChispa("el motor no tiene el tokenizador de e5") }
        return stride(from: 0, to: d.count - 3, by: 4).map { i in
            let v = UInt32(d[d.startIndex + i]) | UInt32(d[d.startIndex + i + 1]) << 8
                | UInt32(d[d.startIndex + i + 2]) << 16 | UInt32(d[d.startIndex + i + 3]) << 24
            return Int64(Int32(bitPattern: v))
        }
    }
}

/// El ONNX de L2: ids → S ∈ R^{K×d}, aplanado por filas.
public protocol SesionRanuras: AnyObject {
    func ranuras(_ ids: [Int64]) throws -> Ranuras
}

public struct Ranuras: Equatable {
    public let datos: [Float]
    public let k: Int

    public init(datos: [Float], k: Int) {
        precondition(k > 0 && datos.count % k == 0, "ranuras: \(datos.count) valores no caben en \(k) filas")
        self.datos = datos
        self.k = k
    }

    /// float32 little endian (iOS y macOS son little endian), que es lo que espera `puntuarL2`.
    public func aBytes() -> Data {
        datos.withUnsafeBufferPointer { Data(buffer: $0) }
    }
}

/// L2: ranuras del mensaje (ONNX Runtime) contra las torres de ESQUEMAS. Si el fichero no trae torres para la
/// pregunta no opina y no llega a tokenizar ni a llamar a ONNX. Si el fichero trae CONJ y L0 ya dio probabilidades,
/// es L2c: las similitudes salen de las mismas ranuras y la cabeza conjunta (en Go, la del servidor) decide; sin
/// cabeza para la pregunta, cae a L2 a secas. Con `codificador`, un esquema que ESQUEMAS no trae (zero-shot) recibe sus
/// torres al vuelo la primera vez (`torresAlVuelo`) y el motor las cachea; sin él, no opina, como antes.
struct CapaL2: Capa {
    let motor: Motor
    let sesion: SesionRanuras
    let tokenizador: Tokenizador
    var codificador: CodificadorTorre? = nil
    /// Reloj monótono en ns (no salta si el usuario o NTP cambian la hora).
    var ahora: () -> UInt64 = { DispatchTime.now().uptimeNanoseconds }
    /// Cuánto tiempo (ns) no se reintenta la torre de un esquema cuyo cálculo falló.
    var ttlFalloTorreNs: UInt64 = 60 * 1_000_000_000
    var nombre: String { "L2" }
    /// Caché negativa: esquema (JSON de la pregunta) → instante hasta el que no se reintenta calcular su torre.
    private let fallosTorre = FallosTorre()

    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa {
        try decidir(texto, pregunta, previas: [:])
    }

    func decidir(_ texto: String, _ pregunta: Pregunta, previas: [String: SalidaCapa]) throws -> SalidaCapa {
        if !pregunta.scoreIdsValidos { return .sinOpinion } // score con ids que no son 1..K: no opina, sin tokenizar ni ONNX
        let pj = pregunta.json()
        // «Esquema nuevo» lo dice el motor en su respuesta (`esquema_nuevo`: ESQUEMAS no trae las torres), no esta capa.
        if !motor.torresL2(pj) {
            guard try torresAlVuelo(pj) else { return .sinOpinion }
        }
        let ventanas: [[Int64]]
        let mensaje = normalizarMayusculas(texto) // contrato de normalización: solo el mensaje de L2, antes de «query: » y de ventanear
        if let tt = tokenizador as? TokenizadorTrozos { ventanas = try tt.trozos(mensaje) } else { ventanas = [try tokenizador.ids(mensaje)] }
        guard let primera = ventanas.first, !primera.isEmpty else { return .sinOpinion }
        if ventanas.count > 1 { return try decidirTrozos(pj, ventanas, previas) } // texto largo con `trozos`
        let s = try sesion.ranuras(primera)
        if let l0 = previas["L0"]?.probs, !l0.isEmpty, motor.tieneConj() {
            let c = try SalidaCapa.desdeJson(motor.cabezaConjunta(try entradaConj(pj, l0, s)))
            if c.opina { return c }
        }
        let r = try SalidaCapa.desdeJson(motor.puntuarL2(pj, ranuras: s.aBytes(), k: s.k))
        // con CONJ, esta es L2 base: respaldo de la cabeza
        return motor.tieneConj() ? SalidaCapa(respuesta: r.respuesta, confianza: r.confianza, probs: r.probs, esquemaNuevo: r.esquemaNuevo,
                                              respuestas: r.respuestas, respaldo: true) : r
    }

    /// Texto largo con `trozos`: ONNX en cada ventana y el motor agrega; con CONJ y L0, la cabeza conjunta decide cada una (como el servidor).
    private func decidirTrozos(_ pj: String, _ ventanas: [[Int64]], _ previas: [String: SalidaCapa]) throws -> SalidaCapa {
        let ss = try ventanas.map { try sesion.ranuras($0) }
        if let l0 = previas["L0"]?.probs, !l0.isEmpty, motor.tieneConj() {
            let c = try SalidaCapa.desdeJson(motor.cabezaConjunta(try entradaConjTrozos(pj, l0, ss)))
            if c.opina { return c }
        }
        var bytes = Data()
        for s in ss { bytes.append(s.aBytes()) }
        let ks = "[" + ss.map { String($0.k) }.joined(separator: ",") + "]"
        let r = try SalidaCapa.desdeJson(motor.puntuarL2Trozos(pj, ranuras: bytes, ksJson: ks))
        return motor.tieneConj() ? SalidaCapa(respuesta: r.respuesta, confianza: r.confianza, probs: r.probs, esquemaNuevo: r.esquemaNuevo,
                                              respuestas: r.respuestas, respaldo: true) : r
    }

    private func entradaConjTrozos(_ preguntaJson: String, _ l0: [String: Double], _ ss: [Ranuras]) throws -> String {
        guard var o = (try JSONSerialization.jsonObject(with: Data(preguntaJson.utf8))) as? [String: Any] else {
            throw ErrorChispa("la pregunta no es un objeto JSON")
        }
        o["l0"] = l0
        o["ranuras"] = ss.flatMap { $0.datos.map { Double($0) } }
        o["k"] = ss[0].k
        o["ks"] = ss.map { $0.k }
        return String(decoding: try JSONSerialization.data(withJSONObject: o), as: UTF8.self)
    }

    private func torresAlVuelo(_ preguntaJson: String) throws -> Bool {
        guard let enc = codificador else { return false }
        let textos = motor.textosTorreL2(preguntaJson)
        if textos.isEmpty { return false }
        if let hasta = fallosTorre.hasta(preguntaJson) {
            if ahora() < hasta { return false } // falló hace poco: no se recalculan N pasadas de la torre
            fallosTorre.olvidar(preguntaJson)
        }
        do {
            let torres = try textos.map { try enc.torre($0) }
            let d = torres[0].count
            guard d > 0, torres.allSatisfy({ $0.count == d }) else {
                throw ErrorChispa("L2: el codificador de torres devolvió dimensiones distintas")
            }
            let plano = torres.flatMap { $0 }
            let bytes = plano.withUnsafeBufferPointer { Data(buffer: $0) } // float32 little endian
            guard motor.instalarTorresL2(preguntaJson, torres: bytes, n: torres.count) else {
                throw ErrorChispa("L2: el motor rechazó las torres al vuelo (d=\(d), n=\(torres.count))")
            }
            return true
        } catch {
            fallosTorre.anotar(preguntaJson, hasta: ahora() &+ ttlFalloTorreNs)
            throw error // la primera vez llega a la cascada, que la registra
        }
    }

    private func entradaConj(_ preguntaJson: String, _ l0: [String: Double], _ s: Ranuras) throws -> String {
        guard var o = (try JSONSerialization.jsonObject(with: Data(preguntaJson.utf8))) as? [String: Any] else {
            throw ErrorChispa("la pregunta no es un objeto JSON")
        }
        o["l0"] = l0
        o["ranuras"] = s.datos.map { Double($0) } // float → double es exacto; Go lo vuelve a float32
        o["k"] = s.k
        return String(decoding: try JSONSerialization.data(withJSONObject: o), as: UTF8.self)
    }
}

/// Caja de la caché negativa de torres (`CapaL2` es un struct: el estado mutable vive en una referencia).
final class FallosTorre {
    private var hastas: [String: UInt64] = [:]
    private let cerrojo = NSLock()
    private let maximo = 256

    func hasta(_ clave: String) -> UInt64? {
        cerrojo.lock(); defer { cerrojo.unlock() }
        return hastas[clave]
    }

    func olvidar(_ clave: String) {
        cerrojo.lock(); defer { cerrojo.unlock() }
        hastas[clave] = nil
    }

    func anotar(_ clave: String, hasta: UInt64) {
        cerrojo.lock(); defer { cerrojo.unlock() }
        if hastas.count >= maximo { hastas.removeAll() }
        hastas[clave] = hasta
    }
}
