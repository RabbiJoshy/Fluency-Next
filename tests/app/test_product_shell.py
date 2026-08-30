import json
from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPOSITORY_ROOT / "app"


class ProductShellTests(unittest.TestCase):
    def test_existing_fluency_entrypoint_and_core_surfaces_are_present(self) -> None:
        html = (APP_ROOT / "index.html").read_text(encoding="utf-8")
        for required_id in (
            "authModal",
            "languageTabs",
            "setupPanel",
            "appContent",
            "flashcard",
            "deckProgressSegments",
            "cardBackScrubber",
            "settingsModal",
        ):
            self.assertIn(f'id="{required_id}"', html)
        self.assertIn('src="js/main.js?v=', html)
        self.assertNotIn('src="src/boot.js"', html)

    def test_complete_existing_runtime_module_set_is_transplanted(self) -> None:
        for filename in (
            "main.js",
            "state.js",
            "ui.js",
            "vocab.js",
            "flashcards.js",
            "progress.js",
            "knowledge.js",
            "speech.js",
            "auth.js",
            "theme.js",
            "data-contracts.js",
        ):
            self.assertTrue((APP_ROOT / "js" / filename).is_file(), filename)
        self.assertFalse((APP_ROOT / "src").exists())

    def test_abandoned_preview_and_csv_paths_are_removed(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (APP_ROOT / "js").glob("*.js")
        )
        self.assertFalse((APP_ROOT / "js" / "speech-vnext.js").exists())
        self.assertNotIn("speechVnext", combined)
        self.assertNotIn("loadCSVFiles", combined)

    def test_card_data_is_available_without_owner_login(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        self.assertIn("label: 'Card data'", flashcards)
        self.assertNotIn("if (!isJstOwner()) return null", flashcards)
        self.assertIn('class="prov-ex-record"', flashcards)
        self.assertIn("['Occurrence', x.occurrence_id]", flashcards)
        self.assertIn("Raw example record", flashcards)
        self.assertIn("Historical retained assignment", flashcards)
        self.assertIn("Release ${esc(releaseId)}", flashcards)

    def test_only_languages_with_clean_releases_are_enabled(self) -> None:
        config = json.loads((APP_ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        enabled = {
            key for key, value in config["languages"].items()
            if value.get("hasData", True)
        }
        self.assertEqual(enabled, {"french", "portuguese", "spanish"})
        self.assertEqual(
            config["languages"]["spanish"]["studyStructurePath"],
            "Data/Spanish/study-structure.json",
        )
        self.assertEqual(
            config["languages"]["spanish"]["releaseManifestPath"],
            "Data/Spanish/release-manifest.json",
        )
        self.assertEqual(
            config["languages"]["spanish"]["releaseCompositionPath"],
            "Data/Spanish/release-composition.json",
        )
        for legacy_path in (
            "conjugatedEnglishPath",
            "ppmDataPath",
        ):
            self.assertNotIn(legacy_path, config["languages"]["spanish"])
        self.assertEqual(
            config["languages"]["spanish"]["conjugationsPath"],
            "Data/Spanish/conjugations.json",
        )
        self.assertNotIn("ppmDataPath", config["languages"]["french"])
        self.assertEqual(
            config["languages"]["french"]["studyStructurePath"],
            "Data/French/study-structure.json",
        )
        self.assertFalse((APP_ROOT / "Data").exists())
        self.assertFalse((APP_ROOT / "Artists").exists())

    def test_merge_lemma_control_is_capability_gated(self) -> None:
        ui = (APP_ROOT / "js" / "ui.js").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            ui.count("lemmaFieldAvailable ? 'block' : 'none'"),
            2,
        )

    def test_language_choice_defers_loading_until_source_choice(self) -> None:
        html = (APP_ROOT / "index.html").read_text(encoding="utf-8")
        ui = (APP_ROOT / "js" / "ui.js").read_text(encoding="utf-8")
        main = (APP_ROOT / "js" / "main.js").read_text(encoding="utf-8")
        config = json.loads((APP_ROOT / "config" / "config.json").read_text(encoding="utf-8"))

        self.assertIn('id="standardSourceSpeechBtn"', html)
        self.assertIn('id="standardSourcePickerBtn"', html)
        self.assertIn("speechSourceButton.onclick", ui)
        self.assertIn("sourceCardButton.onclick = openLyrics", ui)
        self.assertNotIn("sessionStorage.removeItem('fluencyPendingSpeechLanguage');\n            await continueToSpeech();", ui)
        self.assertIn("if (isResumeNavigation && !activeArtist && selectedLanguage === 'spanish')", main)
        self.assertTrue(config["languages"]["spanish"]["capabilities"]["speech"])
        self.assertTrue(config["languages"]["spanish"]["capabilities"]["lyrics"])
        self.assertTrue(config["languages"]["french"]["capabilities"]["speech"])
        self.assertFalse(config["languages"]["french"]["capabilities"]["lyrics"])
        self.assertIn("if (speechSourceButton.disabled) return", ui)

    def test_merge_lemmas_remains_a_declared_learner_feature(self) -> None:
        ui = (APP_ROOT / "js" / "ui.js").read_text(encoding="utf-8")
        config = json.loads((APP_ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(config["languages"]["spanish"]["capabilities"]["mergeLemmas"])
        self.assertIn("window._activeReleaseCapabilities?.mergeLemmas", ui)
        self.assertIn("learner-facing grouping operation over stable surface", ui)

    def test_card_back_omits_only_redundant_single_pos_legend(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        self.assertIn("const hideRedundantSingleBackPos", flashcards)
        self.assertIn("posItems.length === 1", flashcards)
        self.assertIn("!onlyPosHasAction", flashcards)
        self.assertIn("if (!hideRedundantSingleBackPos)", flashcards)

    def test_cognate_setting_uses_positive_inclusion_copy(self) -> None:
        html = (APP_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('<span class="settings-row-label">Cognates', html)
        self.assertIn('data-setting="excludeCognates" data-value="off" aria-pressed="true">Include</button>', html)
        self.assertIn('data-setting="excludeCognates" data-value="on" aria-pressed="false">Exclude</button>', html)

    def test_wsd_publication_view_is_user_selectable(self) -> None:
        html = (APP_ROOT / "index.html").read_text(encoding="utf-8")
        ui = (APP_ROOT / "js" / "ui.js").read_text(encoding="utf-8")
        vocab = (APP_ROOT / "js" / "vocab.js").read_text(encoding="utf-8")
        self.assertIn('data-wsd-publication="forced_leaf"', html)
        self.assertIn('data-wsd-publication="supported_specificity"', html)
        self.assertIn("window.setWsdPublicationProjection", ui)
        self.assertIn("target.searchParams.set('wsdPublication', projection)", vocab)

    def test_active_set_keeps_existing_interaction_model(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        vocab = (APP_ROOT / "js" / "vocab.js").read_text(encoding="utf-8")
        for behavior in (
            "flipCard",
            "handleSwipeAction",
            "cycleExample",
            "showEndOfDeckOptions",
            "deckProgressSegments",
        ):
            self.assertIn(behavior, flashcards)
        self.assertIn('id="cardBackScrubber"', (APP_ROOT / "index.html").read_text(encoding="utf-8"))
        self.assertIn("saveStudySessionSnapshot", flashcards)
        self.assertIn("buildFocusedReviewCard", vocab)

    def test_unassigned_dictionary_menu_does_not_claim_wsd_confidence(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        css = (APP_ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("if (!m.unassigned)", flashcards)
        self.assertIn("hasAssignedEvidence", flashcards)
        self.assertIn("pos-pill-unassigned", flashcards)
        self.assertIn(".pos-collapsible .pos-pill-unassigned", css)

    def test_collapsed_sense_group_uses_measured_overflow_and_clear_hierarchy(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        css = (APP_ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("function fitPosSectionSummaries(root)", flashcards)
        self.assertIn("summary.scrollWidth <= summary.clientWidth + 1", flashcards)
        self.assertIn('class="pos-summary-sense"', flashcards)
        self.assertIn('class="pos-pill-more" hidden', flashcards)
        self.assertIn("fitPosSectionSummaries(backEl)", flashcards)
        self.assertIn("fitPosSectionSummaries(document.getElementById('backContent'))", flashcards)
        self.assertIn(".pos-collapsible .pos-section-summary", css)
        self.assertIn("font-size: 16px", css)
        self.assertIn("citationShownInSenseRows", flashcards)
        self.assertIn('class="pos-pill-pct sense-percentage"', flashcards)
        self.assertIn('class="sense-percentage sense-percentage-tail"', flashcards)
        self.assertIn(".sense-percentage", css)
        self.assertIn("border-left: 1px solid rgba(var(--sense-match-rgb), 0.38)", css)
        self.assertIn('class="pos-pill-lemma"', flashcards)
        self.assertNotIn("headword-group-label", flashcards)
        self.assertNotIn("headword-group-label", css)

    def test_multi_pos_controls_use_bounded_grid_without_reordering_senses(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        css = (APP_ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("pos-count-${Math.min(allPOS.length, 4)}", flashcards)
        self.assertIn("pos-count-${Math.min(posItems.length, 4)}", flashcards)
        self.assertIn("pos === activeDisplayPos ? 'is-active' : 'is-inactive'", flashcards)
        self.assertIn("function orderMeaningEntriesForDisplay(meanings)", flashcards)
        self.assertNotIn("[entries[activeIndex]", flashcards)
        self.assertIn("const orderedMembers = members;", flashcards)
        self.assertIn("activeSense.scrollIntoView", flashcards)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)
        self.assertIn(".card-pos-list.pos-count-3 > :last-child", css)
        self.assertNotIn("pos-peek-stack", css)

    def test_optional_conjugations_join_by_dictionary_headword_not_identity_lemma(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        self.assertIn(
            "currentMeaning?.headword || card.lemma || card.targetWord",
            flashcards,
        )
        self.assertIn("currentMeaning.cycle_pos", flashcards)

    def test_approved_numbered_scrubber_animation_is_retained(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        css = (APP_ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("Numbered active-set scrubber", flashcards)
        self.assertIn("deck-scrubber-lens", css)
        self.assertIn(".deck-progress-segment.is-current", css)

    def test_light_theme_does_not_turn_primary_study_action_white(self) -> None:
        html = (APP_ROOT / "index.html").read_text(encoding="utf-8")
        light_css = (APP_ROOT / "css" / "light-theme.css").read_text(encoding="utf-8")
        worker = (APP_ROOT / "service-worker.js").read_text(encoding="utf-8")

        pale_unstarted_selector = (
            ':root[data-theme="light"] '
            '.range-btn-new:not(.study-set-start):not(.has-progress):not(:hover)'
        )
        self.assertIn(pale_unstarted_selector, light_css)
        self.assertNotIn(
            '.range-btn-new:not(.has-progress):not(:hover)',
            light_css,
        )
        self.assertIn('css/light-theme.css?v=20260828a', html)
        self.assertIn('/css/light-theme.css?v=20260828a', worker)

    def test_active_release_aliases_are_never_cached(self) -> None:
        worker = (APP_ROOT / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn("vocabulary\\.(?:index|examples)", worker)
        self.assertIn("study-structure", worker)
        self.assertIn("release-(?:manifest|composition)", worker)
        self.assertIn("conjugations", worker)
        self.assertIn("pathname === '/config/artists.json'", worker)
        self.assertIn("pathname.startsWith('/Artists/')", worker)
        self.assertIn("cache: 'no-store'", worker)
        self.assertIn("matchInstalledLyricsCatalog", worker)
        self.assertIn("exact immutable catalog", worker)

    def test_artist_catalog_is_validated_and_loads_release_provenance(self) -> None:
        main = (APP_ROOT / "js" / "main.js").read_text(encoding="utf-8")
        contracts = (APP_ROOT / "js" / "data-contracts.js").read_text(encoding="utf-8")
        config = (APP_ROOT / "js" / "config.js").read_text(encoding="utf-8")
        self.assertIn("validateArtistCatalog", main)
        self.assertIn("config/artists.json?contract=lyrics-v1", main)
        self.assertIn("export function validateArtistCatalog", contracts)
        self.assertIn("await loadReleaseProvenance(selectedLanguage)", main)
        self.assertIn("const releaseConfig = activeArtist || languageConfig", config)
        self.assertIn("layers[`artist:${activeArtist.slug}`]", config)

    def test_lyrics_preview_and_resume_are_bound_to_an_exact_release(self) -> None:
        main = (APP_ROOT / "js" / "main.js").read_text(encoding="utf-8")
        vocab = (APP_ROOT / "js" / "vocab.js").read_text(encoding="utf-8")
        self.assertIn("lyricsRelease", main)
        self.assertIn("bindArtistCatalogToRelease", main)
        self.assertIn("requestedReleaseId || artist.releaseId", main)
        self.assertIn("'spotifyPath'", main)
        self.assertIn("activeArtist?.spotifyPath", vocab)
        self.assertIn("releaseId: activeArtist ? currentLyricsReleaseId()", vocab)
        self.assertIn("studySessionMatchesCurrentRelease", vocab)
        self.assertIn("url.searchParams.set('lyricsRelease', snapshot.releaseId)", vocab)
        self.assertIn("if (cachedExamples)", vocab)

    def test_spotify_login_uses_deployable_public_configuration(self) -> None:
        config = json.loads((APP_ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        auth = (APP_ROOT / "js" / "auth.js").read_text(encoding="utf-8")
        spotify = (APP_ROOT / "js" / "spotify.js").read_text(encoding="utf-8")
        html = (APP_ROOT / "index.html").read_text(encoding="utf-8")
        worker = (APP_ROOT / "service-worker.js").read_text(encoding="utf-8")

        client_id = config["publicServices"]["spotifyClientId"]
        self.assertRegex(client_id, r"^[A-Za-z0-9]{16,128}$")
        self.assertIn("config?.publicServices?.spotifyClientId", auth)
        self.assertIn("secrets.spotifyClientId || window._spotifyClientId", auth)
        self.assertIn("Spotify sign-in is temporarily unavailable", spotify)
        self.assertIn("window.open('about:blank', 'spotify-auth'", spotify)
        self.assertIn("spotifyLogin(trackId, positionMs, options.authPopup)", spotify)
        self.assertIn("Popup blocked; redirecting to Spotify auth", spotify)
        self.assertIn("function _loadSpotifyPlaybackSdk()", spotify)
        self.assertNotIn("function _loadSpotifyPlaybackSdk() {\n    if (_isMobile) return", spotify)
        self.assertNotIn("if (_isMobile || !isSpotifyConnected()", spotify)
        self.assertIn("_player.activateElement()", spotify)
        self.assertIn("_activateMobileSdkElementFromGesture();", spotify)
        self.assertLess(
            spotify.index("_activateMobileSdkElementFromGesture();"),
            spotify.index("const authPopup = !_isMobile"),
        )
        self.assertIn("await _mobileSdkIsReadyForPlayback()", spotify)
        self.assertIn("return await _playViaConnect(trackId, positionMs, token)", spotify)
        self.assertIn("_playbackBackend === 'sdk'", spotify)
        self.assertIn("_playbackBackend === 'connect'", spotify)
        self.assertLess(
            spotify.index("window.onSpotifyWebPlaybackSDKReady ="),
            spotify.index("_loadSpotifyPlaybackSdk();"),
        )
        self.assertNotIn("sdk.scdn.co/spotify-player.js", html)
        self.assertIn("/js/spotify.js?v=20260830a", worker)
        self.assertIn("/js/main.js?v=20260830a", worker)
        self.assertIn("const CACHE_NAME = 'flashcards-v311'", worker)

    def test_progress_sync_uses_deployable_public_configuration(self) -> None:
        config = json.loads((APP_ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        auth = (APP_ROOT / "js" / "auth.js").read_text(encoding="utf-8")
        html = (APP_ROOT / "index.html").read_text(encoding="utf-8")
        main = (APP_ROOT / "js" / "main.js").read_text(encoding="utf-8")
        worker = (APP_ROOT / "service-worker.js").read_text(encoding="utf-8")

        sync_url = config["publicServices"]["progressSyncUrl"]
        self.assertRegex(sync_url, r"^https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec$")
        self.assertIn("config?.publicServices?.progressSyncUrl", auth)
        self.assertIn("secrets.googleScriptUrl || GOOGLE_SCRIPT_URL", auth)
        self.assertIn('js/auth.js?v=20260827a', html)
        self.assertIn("auth.js?v=20260827a", main)
        self.assertIn("/js/auth.js?v=20260827a", worker)

    def test_audit_accounts_and_flags_use_release_provenance(self) -> None:
        auth = (APP_ROOT / "js" / "auth.js").read_text(encoding="utf-8")
        modals = (APP_ROOT / "js" / "flashcards-modals.js").read_text(encoding="utf-8")
        config = json.loads((APP_ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        self.assertIn("new Set(['JST', 'JSTA'])", auth)
        self.assertIn("provenanceJson: JSON.stringify(provenance)", auth)
        self.assertIn("flagId = createFlagId()", auth)
        self.assertIn("`flag|${flagId}`", auth)
        self.assertIn("schemaVersion: 4", auth)
        self.assertIn("function _flagRunProvenance", modals)
        self.assertIn("Attached automatically", modals)
        self.assertIn("Release ID:", modals)
        self.assertEqual(
            config["languages"]["french"]["releaseManifestPath"],
            "Data/French/release-manifest.json",
        )

    def test_song_sets_retain_contributing_artist_slugs(self) -> None:
        song_sets = (APP_ROOT / "js" / "song-sets.js").read_text(encoding="utf-8")
        auth = (APP_ROOT / "js" / "auth.js").read_text(encoding="utf-8")
        self.assertIn("function artistSlugsForSongs", song_sets)
        self.assertIn("artistSlugs,", song_sets)
        self.assertIn("remote.artistSlugs", song_sets)
        self.assertIn("window.reconcileRemoteSongSet = reconcileRemoteSongSet", song_sets)
        self.assertIn("setTimeout(() => controller.abort(), 12000)", song_sets)
        self.assertIn("window.reconcileRemoteSongSet?.()", auth)

    def test_language_switch_clears_source_scoped_runtime_data(self) -> None:
        ui = (APP_ROOT / "js" / "ui.js").read_text(encoding="utf-8")
        song_sets = (APP_ROOT / "js" / "song-sets.js").read_text(encoding="utf-8")
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        vocab = (APP_ROOT / "js" / "vocab.js").read_text(encoding="utf-8")
        self.assertIn("window.clearActiveExamplesData?.()", ui)
        self.assertIn("window.resetLanguageOptionalData?.()", ui)
        self.assertIn("export function clearActiveExamplesData", song_sets)
        self.assertIn("window._cachedExamplesDataPath = resolvedSource", song_sets)
        self.assertIn("function resetLanguageOptionalData", flashcards)
        self.assertIn("window._cachedExamplesDataPath !== langConfig.examplesPath", vocab)

    def test_pilot_interface_remains_a_readable_reference(self) -> None:
        reference = REPOSITORY_ROOT / "docs" / "reference" / "pilot-ui-v1.html"
        self.assertTrue(reference.is_file())
        self.assertIn('id="welcome-screen"', reference.read_text(encoding="utf-8"))

    def test_all_relative_module_imports_resolve(self) -> None:
        import_pattern = re.compile(r'^import\s+.*?(?:from\s+)?["\'](.+?)["\'];?$', re.MULTILINE)
        for module in (APP_ROOT / "js").glob("*.js"):
            for target in import_pattern.findall(module.read_text(encoding="utf-8")):
                if not target.startswith("."):
                    continue
                clean_target = target.split("?", 1)[0]
                resolved = (module.parent / clean_target).resolve()
                with self.subTest(module=module.name, target=target):
                    self.assertTrue(resolved.is_file())


if __name__ == "__main__":
    unittest.main()
