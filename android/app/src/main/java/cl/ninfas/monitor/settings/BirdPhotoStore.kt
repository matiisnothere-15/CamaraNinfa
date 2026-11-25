package cl.ninfas.monitor.settings

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import java.io.ByteArrayInputStream
import java.io.File
import kotlin.math.max
import kotlin.math.roundToInt

class BirdPhotoStore(context: Context) {
    private val appContext = context.applicationContext
    private val preferences = appContext.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    private val photosDir = File(appContext.filesDir, "bird_photos")

    fun readAll(): Map<Int, String> = synchronized(lock) {
        val result = linkedMapOf<Int, String>()
        preferences.all.forEach { (key, value) ->
            if (!key.startsWith(KEY_PREFIX)) return@forEach
            val birdId = key.removePrefix(KEY_PREFIX).toIntOrNull() ?: return@forEach
            val path = value as? String ?: return@forEach
            val file = File(path)
            if (file.isFile && file.length() > 0L) {
                result[birdId] = path
            }
        }
        result
    }

    fun saveFromUri(birdId: Int, uri: Uri?): String? {
        if (uri == null || birdId <= 0) return null
        val bytes = runCatching {
            val stream = if (uri.scheme == "file" && !uri.path.isNullOrBlank()) {
                File(uri.path!!).inputStream()
            } else {
                appContext.contentResolver.openInputStream(uri)
            }
            stream?.use { it.readBytes() }
        }.getOrNull() ?: return null

        if (bytes.isEmpty()) return null

        val orientation = runCatching {
            ExifInterface(ByteArrayInputStream(bytes))
                .getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)

        val decoded = decodeSampledBytes(bytes, MAX_DIMENSION_PX * 2) ?: return null
        val oriented = applyExifOrientation(decoded, orientation)
        val scaled = scaleDownIfNeeded(oriented, MAX_DIMENSION_PX)
        return try {
            saveBitmap(birdId, scaled)
        } finally {
            if (scaled !== oriented) scaled.recycle()
            if (oriented !== decoded) oriented.recycle()
            decoded.recycle()
        }
    }

    fun rotatePhoto(birdId: Int, degrees: Float = 90f): String? {
        if (birdId <= 0) return null
        val path = synchronized(lock) { preferences.getString(keyFor(birdId), null) } ?: return null
        val current = BitmapFactory.decodeFile(path) ?: return null
        val matrix = Matrix().apply { postRotate(degrees) }
        val rotated = Bitmap.createBitmap(current, 0, 0, current.width, current.height, matrix, true)
        return try {
            saveBitmap(birdId, rotated)
        } finally {
            if (rotated !== current) rotated.recycle()
            current.recycle()
        }
    }

    fun saveBitmap(birdId: Int, bitmap: Bitmap): String = synchronized(lock) {
        require(birdId > 0) { "Identificador de ave inválido." }
        photosDir.mkdirs()
        val previousPath = preferences.getString(keyFor(birdId), null)
        val tmpFile = File(photosDir, "tmp_$birdId.jpg")
        val targetFile = File(photosDir, "bird_${birdId}_${System.nanoTime()}.jpg")
        tmpFile.outputStream().use { out ->
            check(bitmap.compress(Bitmap.CompressFormat.JPEG, 88, out)) {
                "No se pudo guardar la fotografía de perfil."
            }
        }
        if (targetFile.exists()) targetFile.delete()
        check(tmpFile.renameTo(targetFile)) {
            tmpFile.delete()
            "No se pudo finalizar el guardado de la fotografía."
        }
        check(preferences.edit().putString(keyFor(birdId), targetFile.absolutePath).commit()) {
            targetFile.delete()
            "No se pudo registrar la fotografía seleccionada."
        }
        if (previousPath != null && previousPath != targetFile.absolutePath) {
            File(previousPath).delete()
        }
        targetFile.absolutePath
    }

    fun remove(birdId: Int) = synchronized(lock) {
        val previousPath = preferences.getString(keyFor(birdId), null)
        preferences.edit().remove(keyFor(birdId)).commit()
        if (previousPath != null) File(previousPath).delete()
        Unit
    }

    private fun decodeSampledBytes(bytes: ByteArray, targetMaxEdge: Int): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        var sampleSize = 1
        val largest = max(bounds.outWidth, bounds.outHeight)
        while (largest / sampleSize > targetMaxEdge * 2) {
            sampleSize *= 2
        }
        val opts = BitmapFactory.Options().apply { inSampleSize = sampleSize }
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)
    }

    private fun applyExifOrientation(bitmap: Bitmap, orientation: Int): Bitmap {
        val matrix = Matrix()
        when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.postScale(-1f, 1f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.postScale(1f, -1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> {
                matrix.postRotate(90f)
                matrix.postScale(-1f, 1f)
            }
            ExifInterface.ORIENTATION_TRANSVERSE -> {
                matrix.postRotate(270f)
                matrix.postScale(-1f, 1f)
            }
            else -> return bitmap
        }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
    }

    private fun scaleDownIfNeeded(bitmap: Bitmap, maxEdge: Int): Bitmap {
        val largest = max(bitmap.width, bitmap.height)
        if (largest <= maxEdge || largest <= 0) return bitmap
        val ratio = maxEdge.toFloat() / largest.toFloat()
        val w = (bitmap.width * ratio).roundToInt().coerceAtLeast(1)
        val h = (bitmap.height * ratio).roundToInt().coerceAtLeast(1)
        return Bitmap.createScaledBitmap(bitmap, w, h, true)
    }

    private fun keyFor(birdId: Int) = "$KEY_PREFIX$birdId"

    private companion object {
        const val PREFERENCES_NAME = "ninfas_bird_photos"
        const val KEY_PREFIX = "photo_"
        const val MAX_DIMENSION_PX = 512
        val lock = Any()
    }
}
