# Web Services Interface

Luculent exposes a local HTTP interface on `127.0.0.1`. The Windows and Linux launchers select an available port and print the address. Docker uses port `5000`. Request and response bodies use JSON. There is no authentication yet. Users are identified by `username`. Usernames keep their capitalization but lookup is case-insensitive.

Errors are returned as JSON in this form:

```json
{"error": "description of the problem"}
```

## Test Client

### `GET /`

Returns the HTML test client.

## Users

### `GET /users`

Returns all users.

Response:

```json
{
  "users": [
    {"id": 1, "username": "BigDog"}
  ]
}
```

### `POST /users`

Creates a user. Returns `201 Created`, or `409 Conflict` when the name is already in use regardless of capitalization.

Request:

```json
{"username": "BigDog"}
```

Response:

```json
{"user": {"id": 1, "username": "BigDog"}}
```

## Documents

### `GET /documents?username={username}`

Returns the user's documents and their parts. Readability is a value from `0.0` to `1.0`.

Response:

```json
{
  "documents": [
    {
      "id": 10,
      "title": "사라진 열쇠",
      "language": "Korean",
      "imported": "2026-08-12",
      "parts": [
        {
          "id": 20,
          "position": 0,
          "text": "Document part text...",
          "readability": 0.95,
          "active": true
        }
      ]
    }
  ]
}
```

### `POST /documents`

Imports one URL or text file for a user. The first Korean import downloads and installs the Korean Basic Dictionary. Returns the imported document with `201 Created`.

URL import uses JSON:

Request:

```json
{
  "username": "BigDog",
  "url": "https://example.com/article"
}
```

File import uses `multipart/form-data` with these fields:

- `username`: user name
- `file`: text file

The response has the same document structure used by `GET /documents`:

Response:

```json
{"document": {"id": 10, "title": "Article", "language": "Korean", "imported": "2026-08-12", "parts": []}}
```

### `DELETE /documents/{document_id}`

Deletes a document belonging to the user. Its words remain associated with the user. Returns `204 No Content`.

Request:

```json
{"username": "BigDog"}
```

### `GET /lexicon-status`

Reports whether the Korean lexicon is installed in the configured database.

Response:

```json
{"installed": true}
```

## Document Parts

### `GET /doc-parts/{doc_part_id}?username={username}`

Returns a user-owned document part. `marked_text` surrounds words that are not known or suspended with `**` for display by the reader.

Response:

```json
{
  "doc_part": {
    "id": 20,
    "position": 0,
    "text": "Original text...",
    "marked_text": "Original **text**...",
    "readability": 0.95,
    "active": true
  }
}
```

### `POST /doc-parts/{doc_part_id}/activate`

Makes this part the user's only active document part.

Request:

```json
{"username": "BigDog"}
```

Returns the activated part as `{"doc_part": {...}}`.

## Study

### `GET /get-due-word?username={username}&exclude_word_id={word_id}`

Returns one random due word from the active document part. `exclude_word_id` is optional and prevents immediately returning that word. The service first selects words due now; when none are due, it looks ahead 20 minutes.

When no word is available:

Response:

```json
{"word": null}
```

When a word is available:

Response:

```json
{
  "word": {
    "id": 30,
    "lemma": "열리다",
    "language": "Korean",
    "part_of_speech": "Verb",
    "status": "Learning",
    "due": "2026-08-12T18:30:00+00:00",
    "meanings": [
      {
        "id": 40,
        "korean_definition": "닫힌 것이 풀리다.",
        "english_definition": "For something closed to become open.",
        "gloss": "open"
      }
    ],
    "user_meanings": []
  }
}
```

### `GET /due-count?username={username}`

Returns the dashboard count. It includes only words due now.

Response:

```json
{"due_count": 4}
```

### `GET /study-due-count?username={username}`

Returns the study-session count. It includes words due now and words due within the next 20 minutes.

Response:

```json
{"due_count": 6}
```

### `POST /words/{word_id}/response`

Records a study response. Valid responses are `Again`, `Hard`, `Good`, `Easy`, and `Known`, without regard to capitalization. `duration_ms` is optional and must not be negative. `Known` removes the word from future review; the other responses update its FSRS schedule.

Request:

```json
{
  "username": "BigDog",
  "response": "Good",
  "duration_ms": 2400
}
```

Returns the updated word and the lookahead-inclusive study count:

Response:

```json
{"word": {}, "due_count": 5}
```

## User Meanings

### `POST /words/{word_id}/user-meanings`

Adds a user-owned meaning. At least one definition or gloss must be non-empty.

Request:

```json
{
  "username": "BigDog",
  "korean_definition": "사용자 정의",
  "english_definition": "A definition supplied by the user.",
  "gloss": "my meaning"
}
```

Returns `201 Created`:

Response:

```json
{
  "user_meaning": {
    "id": 50,
    "word_id": 30,
    "korean_definition": "사용자 정의",
    "english_definition": "A definition supplied by the user.",
    "gloss": "my meaning"
  }
}
```

### `DELETE /user-meanings/{user_meaning_id}`

Deletes a meaning created by the user. Lexicon meanings cannot be deleted. Returns `204 No Content`.

Request:

```json
{"username": "BigDog"}
```
