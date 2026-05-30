{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AuditorOutput",
  "type": "object",
  "required": ["score_tono", "observaciones", "oportunidades_mejora"],
  "additionalProperties": false,
  "properties": {
    "score_tono": {
      "type": "integer",
      "minimum": 0,
      "maximum": 15
    },
    "observaciones": {
      "type": "string",
      "maxLength": 400
    },
    "oportunidades_mejora": {
      "type": "array",
      "items": { "type": "string", "maxLength": 200 },
      "maxItems": 10
    }
  }
}
