# Правила проекта SieshKa-Site

## Workflow

### Ветки

- `main` — основная ветка для продакшена. Пушить напрямую **запрещено**.
- `hot-refactor` — ветка для срочных правок и горячего рефакторинга. Изменения мержатся в `main` через `git merge` или `git pull`, pull requests **запрещены**.
- `refactor/clean-architecture` — долгосрочные рефакторинги и новые функции.
- `Stable-*`, `prod-*` — стабильные версии для продакшена.

### Правила

1. **Все изменения** сначала в `hot-refactor` (для срочных правок) или в feature-ветку.
2. **Пушить в main napрямую запрещено.**
3. **Pull requests запрещены.** Слияние выполняется через `git merge` или `git pull` локально.
4. **Pre-commit hooks** могут блокировать коммит. Используй `--no-verify` для пропуска: `git commit --no-verify`.
5. **Миграции Alembic** — проверяй корректность `revision` и `down_revision` ID (стиль: `000N_description` или `000N_description_name`).
6. **Окружение** — настройки хранятся в `.env`, не коммить secrets.

### Команды

```bash
# Применение миграций
docker compose exec api alembic upgrade head

# Пропуск pre-commit
git commit --no-verify -m "message"

# Слияние hot-refactor в main
git checkout main
git merge hot-refactor
git push origin main
```
