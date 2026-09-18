plugins {
    id("com.android.application")
}

android {
    namespace = "app.imslp.accompanist"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.imslp.accompanist"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.2.0-alpha1"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
