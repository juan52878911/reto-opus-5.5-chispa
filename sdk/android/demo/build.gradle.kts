plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.chispa.demo"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.chispa.demo"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "0.1"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // El modelo se abre desde el APK con openFd: sin comprimir.
    androidResources { noCompress += "chispa" }
}

kotlin { jvmToolchain(17) }

dependencies {
    implementation(project(":chispa"))
}
