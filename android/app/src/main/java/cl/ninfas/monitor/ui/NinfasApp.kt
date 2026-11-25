package cl.ninfas.monitor.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.MenuBook
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cl.ninfas.monitor.R

// Paleta centralizada — Guía de campo contemporánea
internal val ForestGreen = Color(0xFF005838)
internal val AmberTrigger = Color(0xFFF1BB50)
internal val SageFilter = Color(0xFFDFEADF)
internal val IvoryBackground = Color(0xFFF6F3E9)
internal val InkText = Color(0xFF1C2B24)
internal val SlateSecondary = Color(0xFF52635A)
internal val ClayError = Color(0xFF963D32)
internal val PureWhite = Color(0xFFFFFFFF)
internal val WarmOutline = Color(0xFFDAD3C3)
internal val ClayContainer = Color(0xFFF9ECE9)

// Alias internos conservados para compatibilidad
internal val FeatherGreen = ForestGreen
internal val CrestYellow = AmberTrigger
internal val Ink = InkText
internal val Cloud = IvoryBackground
internal val DividerGreen = WarmOutline

internal val SpeciesSerif = FontFamily.Serif
internal val SystemSans = FontFamily.SansSerif

internal object NinfasSpacing {
    val xs = 4.dp
    val sm = 8.dp
    val md = 12.dp
    val lg = 16.dp
    val xl = 20.dp
    val xxl = 24.dp
    val screenPadding = 20.dp
}

private val BaseTypography = Typography()

internal val NinfasTypography = Typography(
    headlineSmall = BaseTypography.headlineSmall.copy(
        fontFamily = SystemSans,
        fontWeight = FontWeight.SemiBold,
    ),
    titleLarge = BaseTypography.titleLarge.copy(
        fontFamily = SystemSans,
        fontWeight = FontWeight.SemiBold,
    ),
    titleMedium = BaseTypography.titleMedium.copy(
        fontFamily = SystemSans,
        fontWeight = FontWeight.SemiBold,
    ),
    titleSmall = BaseTypography.titleSmall.copy(
        fontFamily = SystemSans,
        fontWeight = FontWeight.Medium,
    ),
    bodyLarge = BaseTypography.bodyLarge.copy(fontFamily = SystemSans),
    bodyMedium = BaseTypography.bodyMedium.copy(fontFamily = SystemSans),
    bodySmall = BaseTypography.bodySmall.copy(fontFamily = SystemSans),
    labelLarge = BaseTypography.labelLarge.copy(fontFamily = SystemSans, fontWeight = FontWeight.Medium),
    labelMedium = BaseTypography.labelMedium.copy(fontFamily = SystemSans),
    labelSmall = BaseTypography.labelSmall.copy(fontFamily = SystemSans),
)

internal fun tabularStyle(style: TextStyle): TextStyle =
    style.copy(fontFamily = SystemSans, fontFeatureSettings = "tnum")

@Composable
fun NinfasTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = ForestGreen,
            onPrimary = PureWhite,
            primaryContainer = SageFilter,
            onPrimaryContainer = ForestGreen,
            secondary = ForestGreen,
            onSecondary = PureWhite,
            secondaryContainer = SageFilter,
            onSecondaryContainer = InkText,
            tertiary = AmberTrigger,
            onTertiary = InkText,
            background = IvoryBackground,
            onBackground = InkText,
            surface = IvoryBackground,
            onSurface = InkText,
            surfaceVariant = PureWhite,
            onSurfaceVariant = SlateSecondary,
            outline = WarmOutline,
            outlineVariant = WarmOutline,
            error = ClayError,
            onError = PureWhite,
            errorContainer = ClayContainer,
            onErrorContainer = ClayError,
        ),
        typography = NinfasTypography,
        content = content,
    )
}

internal enum class Destination(val label: String, val icon: ImageVector) {
    HOME("Inicio", Icons.Outlined.Home),
    HISTORY("Historial", Icons.Outlined.Timeline),
    BIRDS("Mis ninfas", Icons.Outlined.Pets),
    ASSISTANT("Asistente", Icons.AutoMirrored.Outlined.MenuBook),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NinfasApp(model: NinfasViewModel = viewModel()) {
    val state by model.state.collectAsStateWithLifecycle()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var destination by rememberSaveable { mutableIntStateOf(0) }
    var connectionOpen by rememberSaveable { mutableStateOf(false) }

    DisposableEffect(lifecycle, model) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> model.setForeground(true)
                Lifecycle.Event.ON_PAUSE -> model.setForeground(false)
                else -> Unit
            }
        }
        lifecycle.addObserver(observer)
        if (lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) model.setForeground(true)
        onDispose {
            lifecycle.removeObserver(observer)
            model.setForeground(false)
        }
    }

    NinfasTheme {
        if (state.connection.baseUrl.isBlank()) {
            Surface(Modifier.fillMaxSize(), color = IvoryBackground) {
                ConnectionScreen(state, model, firstConnection = true, onClose = {})
            }
        } else {
            Scaffold(
                containerColor = IvoryBackground,
                topBar = {
                    TopAppBar(
                        colors = TopAppBarDefaults.topAppBarColors(
                            containerColor = IvoryBackground,
                            titleContentColor = InkText,
                            actionIconContentColor = InkText,
                        ),
                        title = {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                CockatielMark(Modifier.size(38.dp))
                                Spacer(Modifier.width(NinfasSpacing.md))
                                Column {
                                    Text(
                                        "Ninfas",
                                        style = MaterialTheme.typography.titleLarge.copy(fontFamily = SpeciesSerif),
                                        color = InkText,
                                    )
                                    Text(
                                        "Guía y monitor de jaula",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = SlateSecondary,
                                    )
                                }
                            }
                        },
                        actions = {
                            IconButton(onClick = model::refresh, enabled = !state.loading) {
                                if (state.loading) {
                                    CircularProgressIndicator(
                                        Modifier.size(22.dp),
                                        strokeWidth = 2.dp,
                                        color = ForestGreen,
                                    )
                                } else {
                                    Icon(Icons.Outlined.Refresh, "Actualizar datos", tint = InkText)
                                }
                            }
                            IconButton(onClick = { connectionOpen = true }) {
                                Icon(Icons.Outlined.Settings, "Configurar conexión", tint = InkText)
                            }
                        },
                    )
                },
                bottomBar = {
                    NavigationBar(containerColor = PureWhite) {
                        Destination.entries.forEachIndexed { index, item ->
                            val selected = destination == index
                            NavigationBarItem(
                                selected = selected,
                                onClick = { destination = index },
                                icon = { Icon(item.icon, null) },
                                label = { Text(item.label, maxLines = 2, textAlign = TextAlign.Center) },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = ForestGreen,
                                    selectedTextColor = ForestGreen,
                                    indicatorColor = SageFilter,
                                    unselectedIconColor = SlateSecondary,
                                    unselectedTextColor = SlateSecondary,
                                ),
                            )
                        }
                    }
                },
            ) { padding ->
                Column(Modifier.padding(padding).fillMaxSize()) {
                    DataStatus(state, model::refresh)
                    when (Destination.entries[destination]) {
                        Destination.HOME -> HomeScreen(state, onRecordVisit = model::recordVisit)
                        Destination.HISTORY -> HistoryScreen(
                            state = state,
                            selectHours = model::selectHours,
                            onRecordVisit = model::recordVisit,
                        )
                        Destination.BIRDS -> BirdsScreen(state, model)
                        Destination.ASSISTANT -> AssistantScreen(state, model::ask)
                    }
                }
            }
        }
        if (connectionOpen && state.connection.baseUrl.isNotBlank()) {
            Dialog(
                onDismissRequest = { connectionOpen = false; model.clearConnectionCheck() },
                properties = DialogProperties(usePlatformDefaultWidth = false),
            ) {
                Surface(Modifier.fillMaxSize(), color = IvoryBackground) {
                    ConnectionScreen(
                        state = state,
                        model = model,
                        firstConnection = false,
                        onClose = {
                            connectionOpen = false
                            model.clearConnectionCheck()
                        },
                    )
                }
            }
        }
    }
}

@Composable
internal fun CockatielMark(modifier: Modifier = Modifier) {
    Image(
        painter = painterResource(R.drawable.logo_ninfa),
        contentDescription = "Logo de Ninfas",
        contentScale = ContentScale.Fit,
        modifier = modifier,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ConnectionScreen(
    state: NinfasUiState,
    model: NinfasViewModel,
    firstConnection: Boolean,
    onClose: () -> Unit,
) {
    val context = LocalContext.current
    var url by remember(state.connection.baseUrl) { mutableStateOf(state.connection.baseUrl) }
    var key by remember(state.connection.baseUrl) { mutableStateOf(state.connection.adminKey) }
    var alerts by remember(state.connection.backgroundAlerts) { mutableStateOf(state.connection.backgroundAlerts) }
    var permissionMessage by remember { mutableStateOf<String?>(null) }
    var disconnectConfirm by remember { mutableStateOf(false) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        alerts = granted
        permissionMessage = if (granted) null
        else "Sin permiso de notificaciones. Puedes habilitarlo en los ajustes de Android."
    }
    Scaffold(
        containerColor = IvoryBackground,
        topBar = {
            TopAppBar(
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = IvoryBackground,
                    titleContentColor = InkText,
                    navigationIconContentColor = InkText,
                ),
                title = {
                    Text(
                        if (firstConnection) "Conecta con tus ninfas" else "Conexión",
                        style = MaterialTheme.typography.titleLarge.copy(fontFamily = SpeciesSerif),
                    )
                },
                navigationIcon = {
                    if (!firstConnection) {
                        IconButton(onClick = onClose) {
                            Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Volver")
                        }
                    }
                },
            )
        },
    ) { padding ->
        Column(
            Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(horizontal = NinfasSpacing.xxl, vertical = NinfasSpacing.lg),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            if (firstConnection) {
                CockatielMark(Modifier.size(72.dp))
                Text(
                    "La cámara observa desde tu PC.",
                    style = MaterialTheme.typography.headlineSmall.copy(fontFamily = SpeciesSerif),
                )
                Text(
                    "Este teléfono consulta sus reportes. Usa una dirección HTTPS accesible desde tu red privada.",
                    color = SlateSecondary,
                )
                state.error?.let { Notice(it, true) }
            }
            OutlinedTextField(
                value = url,
                onValueChange = {
                    if (it != url) key = ""
                    url = it
                    model.clearConnectionCheck()
                },
                label = { Text("URL del servidor") },
                placeholder = { Text("https://tu-servidor") },
                supportingText = { Text("HTTPS con certificado válido. localhost apunta a este teléfono.") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = PureWhite,
                    unfocusedContainerColor = PureWhite,
                    focusedBorderColor = ForestGreen,
                    unfocusedBorderColor = WarmOutline,
                ),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = key,
                onValueChange = { key = it },
                label = { Text("Clave administrativa") },
                supportingText = {
                    Text("Para registrar o eliminar aves y consultar el cuaderno. Se guarda cifrada en este dispositivo.")
                },
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = PureWhite,
                    unfocusedContainerColor = PureWhite,
                    focusedBorderColor = ForestGreen,
                    unfocusedBorderColor = WarmOutline,
                ),
                modifier = Modifier.fillMaxWidth(),
            )
            if (url.trim().trimEnd('/') != state.connection.baseUrl && state.connection.baseUrl.isNotEmpty()) {
                Text(
                    "Al cambiar de servidor se borran la clave anterior, los datos y los avisos guardados. Introduce la clave del nuevo servidor.",
                    style = MaterialTheme.typography.bodySmall,
                    color = SlateSecondary,
                )
            }
            OutlinedButton(
                onClick = { model.checkConnection(url) },
                enabled = !state.checking && url.isNotBlank(),
                border = BorderStroke(1.dp, ForestGreen),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = ForestGreen),
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (state.checking) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = ForestGreen)
                    Spacer(Modifier.width(NinfasSpacing.sm))
                }
                Text(if (state.checking) "Comprobando…" else "Comprobar conexión")
            }
            state.checkMessage?.let { Notice(it, state.checkError) }
            HorizontalDivider(color = WarmOutline)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Avisos con la app cerrada", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "Revisión cada 15 minutos como mínimo. Android puede retrasarla; no son avisos instantáneos.",
                        style = MaterialTheme.typography.bodySmall,
                        color = SlateSecondary,
                    )
                }
                Switch(
                    checked = alerts,
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = PureWhite,
                        checkedTrackColor = ForestGreen,
                    ),
                    onCheckedChange = { requested ->
                        if (requested && Build.VERSION.SDK_INT >= 33 &&
                            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                        ) {
                            permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                        } else {
                            alerts = requested
                        }
                    },
                )
            }
            permissionMessage?.let { Notice(it, true) }
            Text(
                "Tras forzar la detención, vuelve a abrir la app para restablecer las revisiones.",
                style = MaterialTheme.typography.bodySmall,
                color = SlateSecondary,
            )
            Button(
                onClick = {
                    val permitted = Build.VERSION.SDK_INT < 33 ||
                        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
                    if (model.saveConnection(url, key, alerts && permitted)) onClose()
                },
                enabled = url.isNotBlank(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = ForestGreen,
                    contentColor = PureWhite,
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (firstConnection) "Guardar conexión" else "Guardar cambios")
            }
            if (!firstConnection) {
                TextButton(onClick = { disconnectConfirm = true }, modifier = Modifier.fillMaxWidth()) {
                    Text("Eliminar conexión y credenciales", color = ClayError)
                }
            }
            Text(
                "El acceso fuera de casa necesita una red privada o un acceso autenticado configurado en tu PC.",
                style = MaterialTheme.typography.bodySmall,
                color = SlateSecondary,
            )
        }
    }
    if (disconnectConfirm) {
        AlertDialog(
            onDismissRequest = { disconnectConfirm = false },
            containerColor = PureWhite,
            title = { Text("¿Eliminar la conexión?", color = InkText) },
            text = { Text("Se borrarán la dirección, la clave guardada y los avisos de este servidor.", color = SlateSecondary) },
            confirmButton = {
                TextButton(onClick = {
                    val deleted = model.disconnect()
                    disconnectConfirm = false
                    if (deleted) onClose()
                }) { Text("Eliminar conexión", color = ClayError) }
            },
            dismissButton = {
                TextButton(onClick = { disconnectConfirm = false }) { Text("Cancelar", color = ForestGreen) }
            },
        )
    }
}

@Composable
internal fun Notice(text: String, error: Boolean = false, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = if (error) ClayContainer else SageFilter,
        border = BorderStroke(1.dp, if (error) ClayError.copy(alpha = 0.45f) else ForestGreen.copy(alpha = 0.25f)),
        shape = MaterialTheme.shapes.medium,
    ) {
        Row(
            Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Icon(
                imageVector = if (error) Icons.Outlined.WarningAmber else Icons.Outlined.Info,
                contentDescription = if (error) "Aviso de error" else "Información",
                tint = if (error) ClayError else ForestGreen,
                modifier = Modifier.size(20.dp),
            )
            Text(
                text = text,
                style = MaterialTheme.typography.bodyMedium,
                color = if (error) ClayError else InkText,
            )
        }
    }
}

@Composable
private fun DataStatus(state: NinfasUiState, refresh: () -> Unit) {
    if (state.error != null) {
        Column(Modifier.fillMaxWidth().padding(horizontal = NinfasSpacing.lg, vertical = NinfasSpacing.xs)) {
            Notice(
                text = if (state.snapshot == null) state.error
                else "Datos antiguos. ${state.error} Toca «Volver a actualizar» para reintentar.",
                error = true,
            )
            TextButton(onClick = refresh, enabled = !state.loading) {
                Text("Volver a actualizar", color = ForestGreen)
            }
        }
    } else if (state.loading && state.snapshot == null) {
        LinearProgressIndicator(
            Modifier.fillMaxWidth(),
            color = ForestGreen,
            trackColor = SageFilter,
        )
    }
}
