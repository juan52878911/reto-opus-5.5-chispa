pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // El AAR de gomobile (gomobile bind -o chispa/libs/chispamovil.aar …). No va a git.
        flatDir { dirs("chispa/libs") }
    }
}

rootProject.name = "chispa-android"
include(":chispa", ":demo")
