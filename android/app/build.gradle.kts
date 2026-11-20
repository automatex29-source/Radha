import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Signing: the upload key is never kept in the repository. If android/signing.properties exists (storeFile,
// storePassword, keyAlias, keyPassword), the release build is signed with it; otherwise it is built unsigned
// and signed afterwards (see android/README.md).
val signingProps = Properties().apply {
    val f = rootProject.file("signing.properties")
    if (f.isFile) f.inputStream().use { load(it) }
}

android {
    namespace = "net.krishai.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "net.krishai.app"
        minSdk = 24
        targetSdk = 36
        // Raise versionCode by 1 for every upload to Google Play.
        versionCode = (project.findProperty("versionCode") as String?)?.toInt() ?: 1
        versionName = (project.findProperty("versionName") as String?) ?: "1.0.0"
    }

    signingConfigs {
        if (signingProps.isNotEmpty()) {
            create("upload") {
                storeFile = rootProject.file(signingProps.getProperty("storeFile"))
                storePassword = signingProps.getProperty("storePassword")
                keyAlias = signingProps.getProperty("keyAlias")
                keyPassword = signingProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (signingProps.isNotEmpty()) signingConfig = signingConfigs.getByName("upload")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("com.google.androidbrowserhelper:androidbrowserhelper:2.5.0")
    implementation("androidx.browser:browser:1.8.0")
}
