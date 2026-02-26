{{/*
Expand the name of the chart.
*/}}
{{- define "aviation.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "aviation.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s" $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "aviation.labels" -}}
helm.sh/chart: {{ include "aviation.name" . }}
app.kubernetes.io/name: {{ include "aviation.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels for backend
*/}}
{{- define "aviation.backend.selectorLabels" -}}
app: {{ include "aviation.fullname" . }}-backend
{{- end }}

{{/*
Backend image
*/}}
{{- define "aviation.backend.image" -}}
{{ .Values.backend.image.registry }}/{{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}
{{- end }}
