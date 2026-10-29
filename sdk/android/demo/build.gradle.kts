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
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // El modelo se abre desde el APK con openFd: sin comprimir.
    androidResources { noCompress += listOf("chispa", "chispa-tok", "json") }
}

kotlin { jvmToolchain(17) }

dependencies {
    implementation(project(":chispa"))

    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test:runner:1.5.2")
}
