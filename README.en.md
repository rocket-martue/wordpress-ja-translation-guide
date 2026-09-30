# wordpress-ja-translation-guide

[日本語](./README.md) | English

A [Claude Skill](https://www.anthropic.com/news/skills) that keeps Japanese translations of WordPress core, plugins, and themes consistent with the [official ja.wordpress.org translation style guide](https://ja.wordpress.org/team/handbook/translation/).

Use it for Japanese localization work in general: translating `.po` / `.pot` files, reviewing existing Japanese translations, and checking strings before you suggest them on [translate.wordpress.org](https://translate.wordpress.org/) or import them as a PTE (Project Translation Editor).

> [!NOTE]
> This English README is a summary. The Skill itself (`SKILL.md` and `references/`) and the translations it produces are in Japanese. For script options, the rule table of `validate_po.py`, and other developer details, see the [Japanese README](./README.md#開発者向け-skillファイルの生成方法).

## What this Skill covers

It reflects the official ja.wordpress.org [translation handbook](https://ja.wordpress.org/team/handbook/translation/) and [translation style guide](https://ja.wordpress.org/team/handbook/translation/translation-style-guide/).

- Never suggest or import machine translations without careful review (stated in the official handbook; unreviewed machine translations can get your suggestions rejected in bulk)
- The translation policy of clarity, originality, and being modern
- Full-width and half-width characters, punctuation, brackets, and Japanese quotation marks (「」)
- The long vowel mark (ー) in katakana words and the use of the middle dot (・)
- Consistent word choices, such as avoiding the passive voice and translating "View XX" as 「〜を表示」
- Placeholders (`%s`, `%d`, `%1$s`, etc.) must match the original exactly in number and type
- Theme names, plugin names, the "WordPress" brand name, and established feature names are not translated
- A snapshot of every entry in the official glossary (as of the retrieval date), plus pointers to the Consistency Tool
- Uncertain word choices are marked `[要確認]` ("needs confirmation") instead of being presented as final
- The `.po` output format is preserved
- **Batch translation workflow**: `scripts/apply_translations.py` writes translations into a `.po` file in batches, and `scripts/validate_po.py` checks them for rule violations. `po_chunk.py` / `po_collect.py` / `po_apply_loop.py` are included for splitting hundreds of strings among multiple translators

Detailed rules and examples are in `references/` (in Japanese):

- [`references/notation-rules.md`](./references/notation-rules.md) — character width, punctuation, brackets, katakana long vowel marks, dates, and placeholders
- [`references/word-choice-rules.md`](./references/word-choice-rules.md) — consistent word choices, writing style, brand names, and how to use the glossary
- [`references/glossary.md`](./references/glossary.md) — a snapshot of the [official glossary](https://translate.wordpress.org/locale/ja/default/glossary/) (the retrieval date and entry count are at the top of the file)
- [`references/contribution-workflow.md`](./references/contribution-workflow.md) — the batch translation workflow, how to use the scripts, and what may and may not be automated
- [`references/parallel-translation-workflow.md`](./references/parallel-translation-workflow.md) — how to split draft translation among subagents in Claude Code
- [`references/glossary-template.md`](./references/glossary-template.md) — a template for the shared term list you prepare before splitting the work

## Usage

### Downloading a .po file

1. Open the project you want to translate on [translate.wordpress.org](https://translate.wordpress.org/)
2. Select "Japanese"
3. Select either Stable or Stable Readme
4. Click Untranslated to show only the untranslated strings
5. Scroll to the bottom of the page, change "all current" to "only matching the filter", then click "Export" to download the `.po` file
6. Ask Claude to translate the downloaded `.po` file
7. Review the translations and fix them as needed
8. Run `python scripts/validate_po.py path/to/ja.po` to catch rule violations that can be detected mechanically
9. Upload the translated `.po` file with "Import Translations" at the bottom of the page on translate.wordpress.org

### Claude Code / Claude.ai (Desktop, Cowork)

1. Download or `git clone` this repository
2. Put the `wordpress-ja-translation-guide/` folder in your Skills directory, or install it as a `.skill` file
3. Ask Claude about WordPress Japanese translation, and the Skill is used automatically

### Installing from a .skill file

Get `wordpress-ja-translation-guide.skill` from the [Releases](../../releases) page of this repository (or from a file shared with you) and install it in Claude.

### Using parallel subagents in Claude Code

For a `.po` file with many untranslated strings, you can let subagents generate draft translations in parallel. The main agent still writes to the `.po` file and runs validation one step at a time. The draft-only agent definition [`assets/agents/po-draft-translator.md`](./assets/agents/po-draft-translator.md) is included, but a Skill cannot register it automatically, so copy it once to your Claude Code agents directory:

```bash
cp ~/.claude/skills/wordpress-ja-translation-guide/assets/agents/po-draft-translator.md ~/.claude/agents/
```

The steps are in [`references/parallel-translation-workflow.md`](./references/parallel-translation-workflow.md). In environments without the Agent tool (such as Claude.ai Desktop or Cowork), this option is not available and the Skill follows the sequential loop in SKILL.md. Parallelizing does not remove the need for human review and a manual Import.

## Notes

- The official glossary in [`references/glossary.md`](./references/glossary.md) is **a snapshot as of the retrieval date**. The glossary keeps changing, so if it differs from the [official page](https://translate.wordpress.org/locale/ja/default/glossary/), the official page is correct. Words that are not in the glossary, or that you are unsure about, are marked `[要確認]`
- Translations produced by this Skill are **drafts**. Always have a human review them before submitting to translate.wordpress.org, whether as suggestions or as an import

## For developers

The following scripts are in `scripts/`. They need Python 3.8 or later and use only the standard library.

| Script | Purpose |
|---|---|
| `package_skill.py` | Builds `dist/wordpress-ja-translation-guide.skill` locally for inspection |
| `update_glossary.py` | Fetches the official glossary and updates the table in `references/glossary.md` (`--check` exits with 1 if there are differences) |
| `validate_po.py` | Checks a `.po` file for rule violations that can be detected mechanically |
| `fix_spacing.py` | Inserts half-width spaces between half-width letters and full-width characters (dry run by default) |
| `apply_translations.py` | Writes translations into a `.po` file in batches |
| `po_chunk.py` / `po_collect.py` / `po_apply_loop.py` | Split untranslated strings into chunks, collect and check draft translations, then apply and validate them |

Release `.skill` files are built by GitHub Actions (`.github/workflows/release.yml`) from the contents of a `vX.Y.Z` tag and attached to [Releases](../../releases) automatically. Run the tests with `python -m unittest discover -s tests`.

See the [Japanese README](./README.md#開発者向け-skillファイルの生成方法) for command options, the rule IDs of `validate_po.py`, and exit codes.

## Contributing

Issues and pull requests are welcome if you find a mistake in the rules or want a rule added.

## License

[GPL-2.0-or-later](./LICENSE)
