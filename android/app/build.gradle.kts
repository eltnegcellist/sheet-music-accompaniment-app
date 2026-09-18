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
        versionCode = 2
        versionName = "0.2.0"
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

dependencies {
    implementation("androidx.webkit:webkit:1.17.0")
}
