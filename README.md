# Luculent

Luculent is a document-targeted vocabulary study application. It extracts vocabulary from imported documents, divides larger documents into manageable sections, estimates readability, and uses spaced repetition to help users study unfamiliar words.

## Features

- Import Korean text files and web pages
- Extract the main text from web pages while removing navigation, advertisements, references, and other unrelated content
- Divide readings into sections of no more than 300 words
- Extract Korean content words and convert them to dictionary form
- Study words from the active document section using FSRS spaced repetition
- Estimate each document section's readability from the user's vocabulary progress

## Planned Features

- Click words in the reader view to see their definitions and optionally return Known or Suspended words to study

## Using Luculent

Create or select a user. Import a Korean text file or web page into the library. Luculent divides the reading into sections and gathers vocabulary for study. Choose a section and make it active to study its words. You can also open each section to read it in which case unknown words are highlighted.

During Study, reveal each word's meanings and select Again, Hard, Good, Easy, or Known. Luculent schedules future reviews from these responses. Known is intended for words you do not expect to ever forget. The library's readability estimates update as your vocabulary knowledge changes.

## Run Luculent

> **Warning:** Luculent does not yet migrate existing databases. After a schema change, delete `luculent.db` or the `luculent_mysql_data` Docker volume and start again. This deletes all user and study data.

Luculent requires internet access for initial setup and supports Python 3.10 through 3.13.

On Windows, double-click `run.bat` or run:

```powershell
.\run.bat
```

On Linux, run:

```bash
chmod +x run.sh
./run.sh
```

The launcher creates `.venv`, installs the required packages, starts Luculent, and opens it in the default browser. Initial setup can take several minutes. Stop Luculent with `Ctrl+C` in the launcher window.

### Run with Docker

Docker can run Luculent without a local Python installation. To use SQLite, run:

```bash
docker compose up --build luculent
```

To use MySQL, run:

```bash
docker compose --profile mysql up --build luculent-mysql
```

Open `http://127.0.0.1:5000` in a browser. Stop the application with `Ctrl+C`. Docker volumes preserve the database when the containers stop or are rebuilt.

## MySQL

The project uses SQLite by default. For a non-Docker application using MySQL, copy `settings.example.txt` to `settings.txt`, set `database=mysql`, and run `docker compose --profile mysql up -d mysql`. The MySQL container listens on host port 32000.
