#Requires -Modules Microsoft.Graph.Authentication, Microsoft.Graph.Applications
<#
.SYNOPSIS
    Fuegt der App-Registrierung "pco-m365baas" die fuer Veeam Backup for Microsoft 365
    benoetigten Microsoft-Graph-Berechtigungen hinzu.

.DESCRIPTION
    Die Berechtigungs-IDs werden zur Laufzeit aus dem Microsoft-Graph-Service-Principal
    des Tenants gelesen, es sind keine GUIDs hartcodiert. Bereits vorhandene
    Berechtigungen der App bleiben erhalten. Existiert die App-Registrierung nicht,
    wird eine Meldung ausgegeben und das Skript beendet.

    Hinweis: Das Skript fuegt die Berechtigungen nur hinzu. Der Admin-Consent muss
    anschliessend im Entra-Portal erteilt werden (API-Berechtigungen > Administratorzustimmung erteilen).
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$AppName = 'pco-m365baas'
)

$ErrorActionPreference = 'Stop'
$graphAppId = '00000003-0000-0000-c000-000000000000' # Microsoft Graph

# Berechtigungen laut Veeam-Screenshot
$permissions = @(
    @{ Name = 'User.Read.All';                    Type = 'Role';  Label = 'Application' }
    @{ Name = 'User.Read.All';                    Type = 'Scope'; Label = 'Delegated'   }
    @{ Name = 'MailboxItem.ImportExport.All';     Type = 'Role';  Label = 'Application' }
    @{ Name = 'MailboxItem.ImportExport';         Type = 'Scope'; Label = 'Delegated'   }
    @{ Name = 'MailboxItem.Read.All';             Type = 'Role';  Label = 'Application' }
    @{ Name = 'MailboxItem.Read';                 Type = 'Scope'; Label = 'Delegated'   }
    @{ Name = 'MailboxFolder.ReadWrite.All';      Type = 'Role';  Label = 'Application' }
    @{ Name = 'MailboxFolder.ReadWrite';          Type = 'Scope'; Label = 'Delegated'   }
)

Connect-MgGraph -Scopes 'Application.ReadWrite.All' -NoWelcome

# App-Registrierung suchen
$apps = @(Get-MgApplication -Filter "displayName eq '$AppName'" -All)
if ($apps.Count -eq 0) {
    Write-Warning "Die App-Registrierung '$AppName' wurde nicht gefunden. Es wurden keine Aenderungen vorgenommen."
    return
}
if ($apps.Count -gt 1) {
    Write-Warning "Es gibt $($apps.Count) App-Registrierungen mit dem Namen '$AppName'. Bitte eindeutig machen. Es wurden keine Aenderungen vorgenommen."
    return
}
$app = $apps[0]
Write-Host "App-Registrierung gefunden: $($app.DisplayName) (AppId $($app.AppId))"

# Microsoft-Graph-Service-Principal fuer die ID-Aufloesung
$graphSp = Get-MgServicePrincipal -Filter "appId eq '$graphAppId'"

# Bestehende Berechtigungen uebernehmen; Graph-Eintrag separat behandeln
$resourceAccess = @()
$graphAccess = [System.Collections.Generic.List[hashtable]]::new()
foreach ($rra in $app.RequiredResourceAccess) {
    $entries = @($rra.ResourceAccess | ForEach-Object { @{ Id = $_.Id; Type = $_.Type } })
    if ($rra.ResourceAppId -eq $graphAppId) {
        $entries | ForEach-Object { $graphAccess.Add($_) }
    }
    else {
        $resourceAccess += @{ ResourceAppId = $rra.ResourceAppId; ResourceAccess = $entries }
    }
}

# Fehlende Berechtigungen ergaenzen
$changed = $false
foreach ($perm in $permissions) {
    $match = if ($perm.Type -eq 'Role') {
        $graphSp.AppRoles | Where-Object { $_.Value -eq $perm.Name -and $_.AllowedMemberTypes -contains 'Application' }
    }
    else {
        $graphSp.Oauth2PermissionScopes | Where-Object { $_.Value -eq $perm.Name }
    }

    if (-not $match) {
        Write-Warning "Berechtigung '$($perm.Name)' ($($perm.Label)) wurde in Microsoft Graph nicht gefunden und wird uebersprungen."
        continue
    }

    $id = [string]$match.Id
    if ($graphAccess | Where-Object { $_.Id -eq $id -and $_.Type -eq $perm.Type }) {
        Write-Host "  vorhanden:  $($perm.Name) ($($perm.Label))"
        continue
    }

    $graphAccess.Add(@{ Id = $id; Type = $perm.Type })
    $changed = $true
    Write-Host "  hinzugefuegt: $($perm.Name) ($($perm.Label))" -ForegroundColor Green
}

if (-not $changed) {
    Write-Host 'Alle Berechtigungen sind bereits vorhanden. Keine Aenderung noetig.'
    return
}

$resourceAccess += @{ ResourceAppId = $graphAppId; ResourceAccess = $graphAccess.ToArray() }

if ($PSCmdlet.ShouldProcess($app.DisplayName, 'RequiredResourceAccess aktualisieren')) {
    Update-MgApplication -ApplicationId $app.Id -RequiredResourceAccess $resourceAccess
    Write-Host "Berechtigungen fuer '$AppName' aktualisiert. Bitte jetzt den Admin-Consent erteilen." -ForegroundColor Cyan
}
