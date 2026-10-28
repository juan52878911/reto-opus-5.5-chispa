plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.chispa.sdk"
    compileSdk = 34

    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin { jvmToolchain(17) }

dependencies {
    // gomobile bind -target=android: L0 y L1 (y la parte de L2 que no es ONNX).
    api(mapOf("name" to "chispamovil", "ext" to "aar"))
    // L2: ONNX Runtime Mobile.
    api("com.microsoft.onnxruntime:onnxruntime-android:1.19.2")

    testImplementation("junit:junit:4.13.2")
    // El org.json de android.jar es un stub que falla en la JVM: este va antes en el classpath de los tests.
    testImplementation("org.json:json:20240303")
}
