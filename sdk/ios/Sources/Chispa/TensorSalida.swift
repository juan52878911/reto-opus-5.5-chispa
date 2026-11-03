import Foundation

/// Un `.chispa` con el ONNX exportado en fp16 sin `keep_io_types` deja la salida como `tensor(float16)`. `leerFloat32` lee
/// los bytes de la salida como float32 si hay 4 por valor, o como float16 (IEEE 754 binary16) si hay 2; con otra cuenta,
/// error claro. `esperados` es el número de valores que dice la forma del tensor.
func leerFloat32(_ bytes: Data, esperados: Int, _ nombre: String) throws -> [Float] {
    if bytes.count == 4 * esperados {
        return bytes.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
    }
    if bytes.count == 2 * esperados {
        return bytes.withUnsafeBytes { Array($0.bindMemory(to: UInt16.self)).map { medioAFloat32($0) } }
    }
    throw ErrorChispa("\(nombre): la salida trae \(bytes.count) bytes para \(esperados) valores (se espera float32 o float16)")
}

/// IEEE 754 binary16 → float32 (con subnormales, ±Inf y NaN); `Float16` de Swift no existe en macOS x86_64.
func medioAFloat32(_ x: UInt16) -> Float {
    let signo = UInt32(x >> 15) << 31
    let exp = UInt32((x >> 10) & 0x1F)
    let man = UInt32(x & 0x3FF)
    let bits: UInt32
    if exp == 0x1F {
        bits = signo | 0x7F80_0000 | (man << 13)
    } else if exp == 0 && man == 0 {
        bits = signo
    } else if exp == 0 {
        var e: Int32 = 127 - 15 + 1
        var m = man
        while m & 0x400 == 0 { m <<= 1; e -= 1 }
        bits = signo | (UInt32(e) << 23) | ((m & 0x3FF) << 13)
    } else {
        bits = signo | ((exp + 127 - 15) << 23) | (man << 13)
    }
    return Float(bitPattern: bits)
}
