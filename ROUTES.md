# Routes (ALIF Discount)

## Public
- `GET /login` – login page (`next` query supported)
- `POST /login` – form submit

## Authenticated
- `GET /logout`
- `GET /dashboard` – stable view-only dashboard
- `GET /contacts` – list + pagination (query: `page`, `per_page`)
- `POST /contacts` – create contact (form fields: `full_name`, `mobile`, `remarks`)
- `GET /api/contacts` – JSON to search contacts (`q`, `limit`)
- `GET /users`
- `GET /requests`
