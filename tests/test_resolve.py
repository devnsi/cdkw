import pytest

from cdkw.config import ProjectConfig
from cdkw.errors import CdkwError
from cdkw.resolve import (
    default_region_order,
    order_regions,
    region_short,
    region_shortcodes,
    resolve_environment,
)

PATTERN = ProjectConfig().branch_pattern


class TestResolveEnvironment:
    def test_explicit_wins_over_branch(self):
        env, provenance = resolve_environment("stage-nft", "feature/ABC-123-x", PATTERN, [])
        assert env == "stage-nft"
        assert provenance == "explicit"

    def test_derived_from_branch(self):
        env, provenance = resolve_environment(None, "feature/ABC-123-some-test", PATTERN, [])
        assert env == "feature-123"
        assert provenance == "from branch feature/ABC-123-some-test"

    def test_branch_without_match_errors_with_known_environments(self):
        with pytest.raises(CdkwError, match="test-main, prod-main"):
            resolve_environment(None, "main", PATTERN, ["test-main", "prod-main"])

    def test_no_branch_errors(self):
        with pytest.raises(CdkwError, match="cannot resolve environment"):
            resolve_environment(None, None, PATTERN, [])

    def test_pattern_without_num_group_errors(self):
        with pytest.raises(CdkwError, match="named group"):
            resolve_environment(None, "feature/x", r"feature/.*", [])


class TestRegionOrdering:
    def test_default_order_puts_primary_first(self, env_config):
        assert default_region_order(env_config, "synth") == [
            "us-east-1",
            "eu-central-1",
            "ap-south-1",
        ]

    def test_destroy_reverses_with_primary_last(self, env_config):
        assert default_region_order(env_config, "destroy") == [
            "ap-south-1",
            "eu-central-1",
            "us-east-1",
        ]

    def test_no_primary_keeps_declaration_order(self, env_config):
        for region in env_config.regions.values():
            region.is_primary = False
        assert default_region_order(env_config, "deploy") == [
            "eu-central-1",
            "us-east-1",
            "ap-south-1",
        ]

    def test_explicit_regions_keep_given_order(self, env_config):
        regions = order_regions(env_config, "deploy", ["ap-south-1", "us-east-1"], False)
        assert regions == ["ap-south-1", "us-east-1"]

    def test_explicit_order_preserved_even_for_destroy(self, env_config):
        regions = order_regions(env_config, "destroy", ["us-east-1", "ap-south-1"], False)
        assert regions == ["us-east-1", "ap-south-1"]

    def test_unknown_region_errors_listing_known(self, env_config):
        with pytest.raises(CdkwError, match="mars-1"):
            order_regions(env_config, "deploy", ["mars-1"], False)

    def test_non_mutating_verbs_default_to_all_regions(self, env_config):
        assert order_regions(env_config, "synth", [], False) == [
            "us-east-1",
            "eu-central-1",
            "ap-south-1",
        ]

    def test_mutating_verbs_require_selection(self, env_config):
        assert order_regions(env_config, "deploy", [], False) is None
        assert order_regions(env_config, "destroy", [], False) is None
        assert order_regions(env_config, "watch", [], False) is None

    def test_watch_accepts_a_single_region(self, env_config):
        assert order_regions(env_config, "watch", ["us-east-1"], False) == ["us-east-1"]

    def test_watch_rejects_multiple_regions(self, env_config):
        with pytest.raises(CdkwError, match="single region"):
            order_regions(env_config, "watch", ["us-east-1", "eu-central-1"], False)

    def test_watch_rejects_all_regions(self, env_config):
        with pytest.raises(CdkwError, match="single region"):
            order_regions(env_config, "watch", [], True)

    def test_all_regions_flag_unlocks_mutating_verbs(self, env_config):
        assert order_regions(env_config, "deploy", [], True) == [
            "us-east-1",
            "eu-central-1",
            "ap-south-1",
        ]
        assert order_regions(env_config, "destroy", [], True) == [
            "ap-south-1",
            "eu-central-1",
            "us-east-1",
        ]


class TestRegionShort:
    @pytest.mark.parametrize(
        ("region", "short"),
        [
            ("us-east-1", "use1"),
            ("eu-central-1", "euc1"),
            ("ap-south-1", "aps1"),
            ("ap-southeast-1", "apse1"),
            ("us-gov-east-1", "usge1"),
            ("us-gov-west-1", "usgw1"),
            ("cn-north-1", "cnn1"),
            ("cn-northwest-1", "cnnw1"),
        ],
    )
    def test_known_regions(self, region, short):
        assert region_short(region) == short

    def test_malformed_region_errors(self):
        with pytest.raises(CdkwError, match="cannot abbreviate"):
            region_short("local")

    def test_shortcodes_map_per_region(self):
        codes = region_shortcodes(["us-east-1", "ap-southeast-1"])
        assert codes == {"us-east-1": "use1", "ap-southeast-1": "apse1"}

    def test_shortcode_collision_errors(self):
        # eu-costly-1 is not a real region; real names no longer collide, so force one.
        with pytest.raises(CdkwError, match="eu-central-1.*eu-costly-1.*euc1"):
            region_shortcodes(["eu-central-1", "eu-costly-1"])
