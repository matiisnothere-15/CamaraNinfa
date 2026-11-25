package cl.ninfas.monitor.data

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/** Translates the existing Spanish API contract without substituting missing observations. */
internal object JsonParsers {
    fun health(body: String): Health = parse {
        JSONObject(body).run {
            Health(string("status"), boolean("base_datos_disponible"), boolean("monitor_activo"),
                nullableString("ultimo_snapshot_utc"), nullableNumber("minutos_sin_reporte"), integer("lotes_pendientes_respaldo"))
        }
    }

    fun metrics(body: String): Map<String, Metric> = parse {
        val json = JSONObject(body)
        buildMap {
            val keys = json.keys()
            while (keys.hasNext()) {
                val name = keys.next()
                val metric = json.getJSONObject(name)
                put(name, Metric(metric.number("valor"), metric.nullableString("estado"), metric.string("fecha")))
            }
        }
    }

    fun history(body: String): List<HistoryPoint> = parse {
        JSONArray(body).objects { HistoryPoint(string("fecha"), string("metrica"), number("valor"), nullableString("estado")) }
    }

    fun actions(body: String): List<ActionEvent> = parse {
        JSONArray(body).objects {
            ActionEvent(string("fecha"), string("accion"), number("duracion"), nullableString("estado"),
                nullableString("notas"), nullableInteger("track"), nullableString("ave"))
        }
    }

    fun recommendations(body: String): List<Recommendation> = parse {
        JSONArray(body).objects { Recommendation(string("nivel"), string("titulo"), string("detalle")) }
    }

    fun birds(body: String): List<Bird> = parse {
        JSONArray(body).objects { Bird(integer("id"), string("nombre"), nullableString("color"), nullableString("notas"), nullableString("registrada")) }
    }

    fun stats(body: String): Stats = parse {
        JSONObject(body).run {
            Stats(getJSONArray("aves").objects {
                BirdStats(integer("id"), string("nombre"), nullableString("color"), integer("comidas"),
                    number("seg_comiendo"), nullableString("ultima_comida"), integer("bebidas"),
                    number("seg_bebiendo"), nullableString("ultima_bebida"))
            }, integer("sin_identificar"))
        }
    }

    fun assistant(body: String): AssistantReply = parse {
        JSONObject(body).run { AssistantReply(string("respuesta"), string("fuente")) }
    }

    fun confirmMutation(body: String): Unit = parse {
        if (!JSONObject(body).boolean("ok")) throw JSONException("Operation not confirmed")
    }

    private inline fun <T> parse(block: () -> T): T = try {
        block()
    } catch (_: JSONException) {
        throw ApiException("Respuesta no válida del servidor. No se han actualizado los datos.")
    }

    private inline fun <T> JSONArray.objects(parseObject: JSONObject.() -> T): List<T> =
        List(length()) { getJSONObject(it).parseObject() }

    private fun JSONObject.string(key: String): String = get(key) as? String
        ?: throw JSONException("Expected string: $key")

    private fun JSONObject.nullableString(key: String): String? =
        if (isNull(key)) null else string(key)

    private fun JSONObject.boolean(key: String): Boolean = get(key) as? Boolean
        ?: throw JSONException("Expected boolean: $key")

    private fun JSONObject.number(key: String): Double {
        val value = (get(key) as? Number)?.toDouble()
        if (value == null || !value.isFinite()) throw JSONException("Expected finite number: $key")
        return value
    }

    private fun JSONObject.nullableNumber(key: String): Double? = if (isNull(key)) null else number(key)

    private fun JSONObject.integer(key: String): Int {
        val value = number(key)
        if (value < Int.MIN_VALUE || value > Int.MAX_VALUE || value % 1.0 != 0.0) {
            throw JSONException("Expected integer: $key")
        }
        return value.toInt()
    }

    private fun JSONObject.nullableInteger(key: String): Int? = if (isNull(key)) null else integer(key)
}
