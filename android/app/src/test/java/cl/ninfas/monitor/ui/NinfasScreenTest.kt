package cl.ninfas.monitor.ui

import android.app.Application
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.media.ExifInterface
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.view.PixelCopy
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import cl.ninfas.monitor.data.ActionEvent
import cl.ninfas.monitor.data.AssistantReply
import cl.ninfas.monitor.data.Bird
import cl.ninfas.monitor.data.BirdStats
import cl.ninfas.monitor.data.Health
import cl.ninfas.monitor.data.HistoryPoint
import cl.ninfas.monitor.data.Metric
import cl.ninfas.monitor.data.Snapshot
import cl.ninfas.monitor.data.Stats
import cl.ninfas.monitor.settings.ConnectionSettings
import java.io.File
import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w412dp-h915dp-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class NinfasScreenTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Before fun resetPhotoPreferences() {
        val app = ApplicationProvider.getApplicationContext<Application>()
        app.getSharedPreferences("ninfas_bird_photos", Context.MODE_PRIVATE).edit().clear().commit()
        File(app.filesDir, "bird_photos").deleteRecursively()
    }

    @Test fun home_distinguishes_absent_metrics_and_degraded_monitor_from_live_data() {
        var state by mutableStateOf(NinfasUiState(now = fixtureTime))
        compose.setContent {
            NinfasTheme { Surface(Modifier.fillMaxSize()) { HomeScreen(state) } }
        }
        compose.onNodeWithText("Sin reportes disponibles").assertIsDisplayed()
        compose.onNodeWithText("Registrar visita").assertIsDisplayed()
        compose.onNodeWithText("Monitor activo").assertDoesNotExist()

        compose.runOnIdle { state = state.copy(snapshot = emptySnapshot()) }
        compose.onNodeWithText("Aún no hay métricas").assertIsDisplayed()
        compose.onNodeWithText("Monitor sin reporte actual").assertIsDisplayed()
        compose.onNodeWithText("El servidor informa un estado degradado.").assertIsDisplayed()
        compose.onNodeWithText("Monitor activo").assertDoesNotExist()

        compose.runOnIdle {
            state = state.copy(snapshot = richSnapshot())
        }
        compose.onNodeWithText("Cómodo").assertIsDisplayed()
        compose.onNodeWithText("1,7 % diagonal/min").assertIsDisplayed()
        capture("home")
    }

    @Test fun native_chart_exposes_selected_values_and_accessible_previous_next_controls() {
        val activity = listOf(0.4, 1.2, 0.8, 2.4, 1.7).mapIndexed { index, value ->
            HistoryPoint(fixtureTime.minusSeconds((4L - index) * 3600).toString(), "Actividad", value, "Normal")
        }
        val moods = listOf("Normal", "Comodo", "Normal", "Estresado", "Comodo").mapIndexed { index, mood ->
            HistoryPoint(fixtureTime.minusSeconds((4L - index) * 3600).toString(), "EstadoAnimo", 0.0, mood)
        }
        compose.setContent {
            NinfasTheme {
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.verticalScroll(rememberScrollState()).padding(20.dp)) {
                        HistoryChart("Estado de ánimo", moods, mood = true)
                        HistoryChart("Actividad", activity, mood = false)
                    }
                }
            }
        }
        compose.onNodeWithText("Cómodo a las ${localHourOnly(fixtureTime.toString())}").assertIsDisplayed()
        compose.onNodeWithText("Corresponde a la jaula completa").assertIsDisplayed()
        compose.onNodeWithText("1,7 % diagonal/min").assertIsDisplayed()
        compose.onAllNodesWithContentDescription("Observación siguiente").onLast().assertIsNotEnabled()
        compose.onAllNodesWithContentDescription("Observación anterior").onLast().performClick()
        compose.onNodeWithText("2,4 % diagonal/min").assertIsDisplayed()
        compose.onAllNodesWithContentDescription("Observación siguiente").onLast().assertIsEnabled().performClick()
        compose.onNodeWithText("1,7 % diagonal/min").assertIsDisplayed()
        compose.onAllNodesWithContentDescription("Observación siguiente").onLast().assertIsNotEnabled()
        capture("history")
    }

    @Test fun assistant_requires_key_and_respects_unicode_limit_without_resending() {
        var state by mutableStateOf(NinfasUiState(connection = ConnectionSettings(baseUrl = "https://fixture.invalid")))
        val submitted = mutableListOf<String>()
        compose.setContent {
            NinfasTheme {
                Surface(Modifier.fillMaxSize()) {
                    AssistantScreen(state) { question ->
                        submitted.add(question)
                        state = state.copy(assistantBusy = true)
                    }
                }
            }
        }
        val questionField = compose.onNode(hasSetTextAction())
        questionField.performTextInput("¿Cómo estuvo la actividad?")
        compose.onNodeWithText("Consultar").assertIsNotEnabled()
        compose.runOnIdle { state = state.copy(connection = state.connection.copy(adminKey = "fixture-test-key")) }
        questionField.performTextReplacement("a".repeat(601))
        compose.onNodeWithText("601/600 caracteres").assertIsDisplayed()
        compose.onNodeWithText("Consultar").assertIsNotEnabled()
        questionField.performTextReplacement("🐦".repeat(600))
        compose.onNodeWithText("600/600 caracteres").assertIsDisplayed()
        compose.onNodeWithText("Consultar").assertIsEnabled()

        val question = "¿Cómo estuvo la actividad?"
        questionField.performTextReplacement(question)
        compose.onNodeWithText("Consultar").performClick()
        compose.onNodeWithText("Consultando…").assertIsNotEnabled()
        compose.runOnIdle {
            assertEquals(listOf(question), submitted)
            state = state.copy(
                assistantBusy = false,
                assistantReply = AssistantReply("Los reportes disponibles describen la actividad de la jaula completa.", "Reportes del monitor"),
            )
        }
        compose.onNodeWithText("Respuesta").assertIsDisplayed()
        compose.onNodeWithText("Fuente: Reportes del monitor").assertIsDisplayed()
        compose.runOnIdle { assertEquals(1, submitted.size) }
        capture("assistant")
    }

    @Test fun bird_profile_photos_persist_across_reopen_and_keep_previous_on_cancel() {
        val app = ApplicationProvider.getApplicationContext<Application>()
        val uriMushuA = createTempImageUri(app, "mushu_a.png", Color.rgb(241, 187, 80))
        val uriYukkiB = createTempImageUri(app, "yukki_b.png", Color.rgb(150, 165, 175))

        val model = createTestModel(richSnapshot())
        compose.setContent { NinfasApp(model) }

        compose.onNodeWithText("Mis ninfas").performClick()
        // Before choosing a photo, both birds show initials and "Añadir foto", plus singular/plural visits
        compose.onNodeWithText("M").assertIsDisplayed()
        compose.onNodeWithText("Y").assertIsDisplayed()
        compose.onAllNodesWithText("Añadir foto").assertCountEquals(2)
        compose.onNode(hasText("1 visita · Tiempo observado: 21,0 s")).assertIsDisplayed()
        compose.onNode(hasText("2 visitas · Tiempo observado: 22,0 s")).assertIsDisplayed()

        // Assign distinct photos to both birds
        compose.runOnIdle {
            model.assignBirdPhoto(1, uriMushuA)
            model.assignBirdPhoto(2, uriYukkiB)
        }
        compose.onAllNodesWithText("Cambiar foto").assertCountEquals(2)
        compose.onNodeWithContentDescription("Retrato de Mushu").assertIsDisplayed()
        compose.onNodeWithContentDescription("Retrato de Yukki").assertIsDisplayed()
        val pathMushuAfterA = model.state.value.birdPhotos[1]
        val pathYukkiB = model.state.value.birdPhotos[2]
        assertNotNull(pathMushuAfterA)
        assertNotNull(pathYukkiB)
        assertNotEquals(pathMushuAfterA, pathYukkiB)

        // Cancel selection (null URI) -> preserves previous photo
        compose.runOnIdle { model.assignBirdPhoto(1, null) }
        assertEquals(pathMushuAfterA, model.state.value.birdPhotos[1])

        // Change only Mushu's photo to an EXIF-rotated 80x40 JPEG (ORIENTATION_ROTATE_90 -> upright 40x80)
        val uriMushuExif90 = createRotatedJpegUri(
            app,
            "mushu_exif90.jpg",
            width = 80,
            height = 40,
            leftColor = Color.rgb(241, 187, 80),
            rightColor = Color.rgb(0, 88, 56),
            exifOrientation = ExifInterface.ORIENTATION_ROTATE_90,
        )
        compose.runOnIdle { model.assignBirdPhoto(1, uriMushuExif90) }
        val pathMushuOriented = model.state.value.birdPhotos[1]!!
        assertNotEquals(pathMushuAfterA, pathMushuOriented)
        val orientedBmp = BitmapFactory.decodeFile(pathMushuOriented)!!
        assertEquals(40, orientedBmp.width)
        assertEquals(80, orientedBmp.height)
        // Left half rotated 90° CW becomes the top half (yellow/amber > green)
        val topPixel = orientedBmp.getPixel(20, 10)
        val bottomPixel = orientedBmp.getPixel(20, 70)
        assertTrue(Color.red(topPixel) > Color.red(bottomPixel))
        orientedBmp.recycle()

        // Tap "Girar" button in UI to rotate 90° clockwise (40x80 -> 80x40)
        compose.onNodeWithTag("bird_rotate_photo_button_1").assertIsDisplayed().performClick()
        val pathMushuRotated = model.state.value.birdPhotos[1]!!
        assertNotEquals(pathMushuOriented, pathMushuRotated)
        val rotatedBmp = BitmapFactory.decodeFile(pathMushuRotated)!!
        assertEquals(80, rotatedBmp.width)
        assertEquals(40, rotatedBmp.height)
        rotatedBmp.recycle()

        // Simulate closing + reopening the app with a new ViewModel
        val reopenedModel = NinfasViewModel(app).apply {
            autoRefreshEnabled = false
            clock = { fixtureTime }
            seedForTest(snapshot = richSnapshot(), now = fixtureTime)
        }
        assertEquals(pathMushuRotated, reopenedModel.state.value.birdPhotos[1])
        assertEquals(pathYukkiB, reopenedModel.state.value.birdPhotos[2])
        capture("birds_field_guide")
    }

    @Test fun caregiver_history_cleans_legacy_strings_and_records_visit_without_creating_images() {
        val app = ApplicationProvider.getApplicationContext<Application>()
        val model = createTestModel(richSnapshot())
        compose.setContent { NinfasApp(model) }

        val filesBefore = app.filesDir.walkTopDown().filter { it.isFile }.count()

        // Record a visit via the UI dialog (Mushu at Bebedero for 5.4 s)
        compose.onNodeWithTag("home_record_visit_button").performClick()
        compose.onNodeWithText("Bebedero").performClick()
        compose.onNodeWithText("Mushu").performClick()
        compose.onNodeWithText("Duración en segundos (opcional)").performTextInput("5.4")
        compose.onNodeWithText("Guardar visita").performClick()

        val filesAfter = app.filesDir.walkTopDown().filter { it.isFile }.count()
        assertEquals("Recording a visit must not create any image file", filesBefore, filesAfter)

        // Home reflects the new visit in natural caregiver language
        compose.onNodeWithText("Mushu visitó el bebedero").assertIsDisplayed()
        compose.onNodeWithText("Estuvo allí 5,4 segundos").assertIsDisplayed()

        // History groups by day, keeps clean caregiver phrasing for new and legacy events, and hides technical strings
        compose.onNodeWithText("Historial").performClick()
        compose.onNodeWithTag("history_list").performScrollToNode(hasText("Mushu visitó el bebedero"))
        compose.onNodeWithText("Mushu visitó el bebedero").assertIsDisplayed()
        compose.onNodeWithText("Estuvo allí 5,4 segundos").assertIsDisplayed()

        compose.onNodeWithTag("history_list").performScrollToNode(hasText("Un ave visitó el comedero"))
        compose.onNodeWithText("Un ave visitó el comedero").assertIsDisplayed()
        compose.onNodeWithText("Estuvo allí 8,2 segundos").assertIsDisplayed()

        listOf("Estado=BEBIENDO", "track 409", "Motivo=track_perdido", "Evidencia=", ".jpg").forEach { forbidden ->
            compose.onAllNodes(hasText(forbidden, substring = true)).assertCountEquals(0)
        }
        capture("history_caregiver")
    }

    private fun createTempImageUri(context: Context, name: String, color: Int): Uri {
        val bmp = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888).apply { eraseColor(color) }
        val file = File(context.cacheDir, name)
        file.outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bmp.recycle()
        return Uri.fromFile(file)
    }

    private fun createRotatedJpegUri(
        context: Context,
        name: String,
        width: Int,
        height: Int,
        leftColor: Int,
        rightColor: Int,
        exifOrientation: Int,
    ): Uri {
        val bmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        for (y in 0 until height) {
            for (x in 0 until width) {
                bmp.setPixel(x, y, if (x < width / 2) leftColor else rightColor)
            }
        }
        val file = File(context.cacheDir, name)
        file.outputStream().use { bmp.compress(Bitmap.CompressFormat.JPEG, 95, it) }
        bmp.recycle()
        ExifInterface(file.absolutePath).apply {
            setAttribute(ExifInterface.TAG_ORIENTATION, exifOrientation.toString())
            saveAttributes()
        }
        return Uri.fromFile(file)
    }

    private fun createTestModel(snapshot: Snapshot): NinfasViewModel {
        val app = ApplicationProvider.getApplicationContext<Application>()
        return NinfasViewModel(app).apply {
            autoRefreshEnabled = false
            clock = { fixtureTime }
            seedForTest(snapshot = snapshot, now = fixtureTime)
        }
    }

    private fun capture(name: String) {
        captureWindowScreenshot(compose, name)
    }

    internal companion object {
        val fixtureTime: Instant = Instant.parse("2026-11-18T15:30:00Z")

        fun emptySnapshot() = Snapshot(
            health = Health("degraded", true, true, fixtureTime.toString(), 0.0, 0),
            metrics = emptyMap(), history = emptyList(), actions = emptyList(),
            recommendations = emptyList(), birds = emptyList(), stats = Stats(emptyList(), 0), fetchedAt = fixtureTime,
        )

        fun richSnapshot() = Snapshot(
            health = Health("ok", true, true, fixtureTime.toString(), 0.5, 0),
            metrics = mapOf(
                "EstadoAnimo" to Metric(3.0, "Comodo", fixtureTime.toString()),
                "Actividad" to Metric(1.7, "Normal", fixtureTime.toString()),
                "Audio" to Metric(0.0, "Tranquilo", fixtureTime.toString()),
                "SinComer" to Metric(0.6, "Normal", fixtureTime.toString()),
                "SinBeber" to Metric(0.3, "Normal", fixtureTime.toString()),
            ),
            history = listOf(
                HistoryPoint(fixtureTime.minusSeconds(3600).toString(), "EstadoAnimo", 0.0, "Normal"),
                HistoryPoint(fixtureTime.toString(), "EstadoAnimo", 0.0, "Comodo"),
                HistoryPoint(fixtureTime.minusSeconds(3600).toString(), "Actividad", 1.1, "Normal"),
                HistoryPoint(fixtureTime.toString(), "Actividad", 1.7, "Normal"),
            ),
            actions = listOf(
                ActionEvent(fixtureTime.minusSeconds(7200).toString(), "Alimentacion", 14.2, "Fin", null, null, "Mushu"),
                ActionEvent(
                    date = fixtureTime.minusSeconds(93600).toString(),
                    action = "Alimentacion",
                    duration = 0.0,
                    state = "Fin",
                    notes = "Estado=BEBIENDO | Duracion=8.2s | Ave=track #409 | Motivo=track_perdido | Evidencia=evidencia_20261117.jpg",
                    track = 409,
                    bird = null,
                ),
            ),
            recommendations = emptyList(),
            birds = listOf(
                Bird(1, "Mushu", "Lutino amarillo y blanco", "Frecuenta el bebedero por la mañana.", fixtureTime.minusSeconds(86400 * 5).toString()),
                Bird(2, "Yukki", "Gris perlado", "Prefiere la percha superior.", fixtureTime.minusSeconds(86400 * 5).toString()),
            ),
            stats = Stats(
                birds = listOf(
                    BirdStats(1, "Mushu", "Lutino", 4, 48.0, fixtureTime.minusSeconds(7200).toString(), 1, 21.0, fixtureTime.minusSeconds(3600).toString()),
                    BirdStats(2, "Yukki", "Gris", 2, 22.0, fixtureTime.minusSeconds(10800).toString(), 2, 14.0, fixtureTime.minusSeconds(93600).toString()),
                ),
                unidentified = 0,
            ),
            fetchedAt = fixtureTime,
        )
    }
}

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w320dp-h568dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class NinfasSmallScreenTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun small_phone_charts_handle_dense_observations_and_data_gaps() {
        val base = NinfasScreenTest.fixtureTime
        // Dense observations: 20 points every 10 minutes with a clear activity peak
        val denseMood = (0 until 20).map { idx ->
            val t = base.minusSeconds((19 - idx) * 600L).toString()
            val state = when {
                idx in 6..8 -> "Estresado"
                idx in 9..13 -> "Normal"
                else -> "Comodo"
            }
            HistoryPoint(t, "EstadoAnimo", 0.0, state)
        }
        val denseActivity = (0 until 20).map { idx ->
            val t = base.minusSeconds((19 - idx) * 600L).toString()
            val value = if (idx == 7) 42.5 else if (idx in 10..15) 2.4 else 8.6
            val state = if (value > 40) "Alta Actividad" else if (value < 5) "Tranquilo" else "Actividad Normal"
            HistoryPoint(t, "Actividad", value, state)
        }

        // Observations with a 3-hour gap (camera stopped / no data)
        val gapMood = listOf(
            HistoryPoint(base.minusSeconds(4 * 3600 + 600).toString(), "EstadoAnimo", 0.0, "Normal"),
            HistoryPoint(base.minusSeconds(4 * 3600).toString(), "EstadoAnimo", 0.0, "Normal"),
            HistoryPoint(base.minusSeconds(600).toString(), "EstadoAnimo", 0.0, "Comodo"),
            HistoryPoint(base.toString(), "EstadoAnimo", 0.0, "Comodo"),
        )
        val gapActivity = listOf(
            HistoryPoint(base.minusSeconds(4 * 3600 + 600).toString(), "Actividad", 12.0, "Actividad Normal"),
            HistoryPoint(base.minusSeconds(4 * 3600).toString(), "Actividad", 18.5, "Actividad Normal"),
            HistoryPoint(base.minusSeconds(600).toString(), "Actividad", 3.1, "Tranquilo"),
            HistoryPoint(base.toString(), "Actividad", 4.0, "Tranquilo"),
        )

        var useGaps by mutableStateOf(false)
        compose.setContent {
            NinfasTheme {
                Surface(Modifier.fillMaxSize(), color = IvoryBackground) {
                    Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp)) {
                        HistoryChart("Estado de ánimo", if (useGaps) gapMood else denseMood, mood = true)
                        HistoryChart("Actividad", if (useGaps) gapActivity else denseActivity, mood = false)
                    }
                }
            }
        }

        compose.onNodeWithText("Cómodo a las ${localHourOnly(base.toString())}").assertIsDisplayed()
        compose.onNodeWithText("Corresponde a la jaula completa").assertIsDisplayed()
        compose.onNodeWithText("Desplazamiento en la jaula (% de la diagonal de cámara por minuto)").performScrollTo().assertIsDisplayed()
        captureWindowScreenshot(compose, "charts_dense_small")

        compose.runOnIdle { useGaps = true }
        compose.onNodeWithText("Estado de ánimo").performScrollTo()
        compose.onAllNodesWithText("Sin datos").onFirst().assertIsDisplayed()
        captureWindowScreenshot(compose, "charts_mood_gaps_small")
        compose.onNodeWithText("La línea se corta en períodos sin mediciones para distinguirlos de baja actividad.").performScrollTo().assertIsDisplayed()
        captureWindowScreenshot(compose, "charts_gaps_small")
    }

    @Test fun small_phone_birds_and_home_with_large_font_remain_legible() {
        val app = ApplicationProvider.getApplicationContext<Application>()
        val model = NinfasViewModel(app).apply {
            autoRefreshEnabled = false
            clock = { NinfasScreenTest.fixtureTime }
            seedForTest(snapshot = NinfasScreenTest.richSnapshot(), now = NinfasScreenTest.fixtureTime)
        }
        compose.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(base.density, fontScale = 1.25f)) {
                NinfasApp(model)
            }
        }
        compose.onNodeWithTag("home_record_visit_button").assertIsDisplayed()
        compose.onNodeWithText("Mis ninfas").performClick()
        compose.onNodeWithText("Mushu").assertIsDisplayed()
        compose.onNodeWithTag("birds_list").performScrollToNode(hasText("Yukki"))
        compose.onNodeWithText("Yukki").assertIsDisplayed()
        captureWindowScreenshot(compose, "birds_small")
    }
}

private fun captureWindowScreenshot(
    compose: androidx.compose.ui.test.junit4.AndroidComposeTestRule<*, ComponentActivity>,
    name: String,
) {
    compose.waitForIdle()
    val bitmap = compose.runOnIdle {
        val window = compose.activity.window
        val view = window.decorView
        assertTrue("Screenshot view has no layout", view.width > 0 && view.height > 0)
        val image = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
        var result = PixelCopy.ERROR_UNKNOWN
        PixelCopy.request(window, image, { result = it }, Handler(Looper.getMainLooper()))
        assertEquals("Native PixelCopy failed", PixelCopy.SUCCESS, result)
        image
    }
    val background = bitmap.getPixel(0, 0)
    val stepX = (bitmap.width / 40).coerceAtLeast(1)
    val stepY = (bitmap.height / 40).coerceAtLeast(1)
    assertTrue("Native screenshot is blank", (0 until bitmap.height step stepY).any { y ->
        (0 until bitmap.width step stepX).any { x -> bitmap.getPixel(x, y) != background }
    })
    val target = File("build/screenshots/$name.png")
    target.parentFile?.mkdirs()
    target.outputStream().use { output ->
        assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, output))
    }
    assertTrue("Screenshot was not written: ${target.absolutePath}", target.length() > 0)
}
