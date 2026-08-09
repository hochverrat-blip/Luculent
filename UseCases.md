# Luculent Use Cases

## Use Case 1: Gather Vocabulary to Study

### Description

The user provides a document or a link to an online document in Korean they wish to read. The application extracts unknown vocabulary from the document, filtering for content words and storing them in lemma form, and creates flash cards for future study.

### Input

A document from disk or a URL to an online document.

### Output

Flash cards stored in the database.

---

## Use Case 2: Study Vocabulary

### Description

The user reviews vocabulary using spaced repetition. The application presents a flash card due for review. The user indicates how well they recalled the answer, and the application updates the flash card data.

### Inputs

- Flash card data from the database
- The user's response for the flash card (Again, Hard, Good, Easy, Known)

### Outputs

- Flash card presented for study
- Updated flash card data stored in the database

---

## Use Case 3: Estimate Document Readability

### Description

The user provides a document or a link to an online document. The application estimates how readable the document is based on the user's current vocabulary knowledge derived from flash card progress.

### Input

A document from disk or a URL to an online document.

### Output

A readability estimate based on the user's current vocabulary knowledge
