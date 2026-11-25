package cl.ninfas.monitor.data

import java.time.Instant

data class Health(
    val status: String,
    val databaseAvailable: Boolean,
    val monitorActive: Boolean,
    val lastSnapshot: String?,
    val minutesWithoutReport: Double?,
    val pendingBatches: Int,
)

data class Metric(val value: Double, val state: String?, val date: String)
data class HistoryPoint(val date: String, val metric: String, val value: Double, val state: String?)
data class ActionEvent(
    val date: String,
    val action: String,
    val duration: Double,
    val state: String?,
    val notes: String?,
    val track: Int?,
    val bird: String?,
)
data class Recommendation(val level: String, val title: String, val detail: String)
data class Bird(val id: Int, val name: String, val color: String?, val notes: String?, val registered: String?)
data class BirdStats(
    val id: Int,
    val name: String,
    val color: String?,
    val foodVisits: Int,
    val foodSeconds: Double,
    val lastFood: String?,
    val waterVisits: Int,
    val waterSeconds: Double,
    val lastWater: String?,
)
data class Stats(val birds: List<BirdStats>, val unidentified: Int)
data class AssistantReply(val answer: String, val source: String)
data class Snapshot(
    val health: Health,
    val metrics: Map<String, Metric>,
    val history: List<HistoryPoint>,
    val actions: List<ActionEvent>,
    val recommendations: List<Recommendation>,
    val birds: List<Bird>,
    val stats: Stats,
    val fetchedAt: Instant,
)
