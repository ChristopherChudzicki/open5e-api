"""Serializers and helper methods for the Creature model."""

from math import floor

from rest_framework import serializers

from api_v2 import models

from .abstracts import GameContentSerializer, prefixed_aggregate_serializer
from .abstracts import DescriptionSerializer
from .damagetype import DamageTypeSummarySerializer
from .condition import ConditionSummarySerializer
from .document import DocumentSummarySerializer
from .language import LanguageSummarySerializer
from .environment import EnvironmentSummarySerializer
from .size import SizeSummarySerializer
from .image import ImageSummarySerializer
from drf_spectacular.utils import extend_schema_field, inline_serializer
from drf_spectacular.types import OpenApiTypes

class CreatureActionAttackSerializer(GameContentSerializer):
    distance_unit = serializers.SerializerMethodField()
    damage_type = DamageTypeSummarySerializer()
    extra_damage_type = DamageTypeSummarySerializer()

    class Meta:
        model = models.CreatureActionAttack
        fields = [
            'name',
            'attack_type',
            'to_hit_mod',
            'reach',
            'range',
            'long_range',
            'target_creature_only',
            'damage_die_count',
            'damage_die_type',
            'damage_bonus',
            'damage_type',
            'extra_damage_die_count',
            'extra_damage_die_type',
            'extra_damage_bonus',
            'extra_damage_type',
            'distance_unit',
        ]

    # todo: type is any
    @extend_schema_field(OpenApiTypes.STR)
    def get_distance_unit(self, CreatureActionAttack):
        return CreatureActionAttack.get_distance_unit


class CreatureActionSerializer(GameContentSerializer):
    attacks = CreatureActionAttackSerializer(many=True, read_only=True)
    usage_limits = serializers.SerializerMethodField()

    class Meta:
        model = models.CreatureAction
        fields = [
            'name',
            'desc',
            'attacks',
            'action_type',
            'order_in_statblock',
            'legendary_action_cost',
            'limited_to_form',
            'usage_limits'
        ]

    # Gathers 'uses_type' and 'uses_param' into a single 'usage_limits' obj.
    def get_usage_limits(self, obj)->dict:
        if obj.uses_type and obj.uses_param: 
            return {
                'type': obj.uses_type,
                'param': obj.uses_param
            }


class CreatureTypeDescriptionSerializer(DescriptionSerializer):
    class Meta:
        model=models.CreatureTypeDescription
        fields=['desc','document','gamesystem']


class CreatureTypeSerializer(GameContentSerializer):
    '''Serializer for the Creature Type object'''
    key = serializers.ReadOnlyField()
    descriptions = CreatureTypeDescriptionSerializer(many=True)

    class Meta:
        '''Meta options for serializer.'''
        model = models.CreatureType
        fields = '__all__'


class CreatureTypeSummarySerializer(GameContentSerializer):
    '''
    A slimmer CreatureTypeSerializer, designed to serialize CreatureType FKs on
    other serializers . Not intended to be used directly with in a ModelViewset.
    '''
    class Meta:
        model = models.CreatureType
        fields = ['name', 'key']


class CreatureTraitSerializer(GameContentSerializer):
    '''Serializer for the Creature Trait object'''
    class Meta:
        model = models.CreatureTrait
        fields = ['name', 'desc']


class CreatureLanguageSerializer(GameContentSerializer):
    as_string = serializers.CharField(source="languages_desc")
    data = LanguageSummarySerializer(source="languages", many=True)

    class Meta:
        model = models.Creature
        fields = ['as_string', 'data']


class CreatureResistancesAndImmunitiesSerializer(GameContentSerializer):
    '''This serializer formats a Creature's damage modifier as a single obj '''
    damage_immunities_display = serializers.CharField()
    damage_immunities = DamageTypeSummarySerializer(many=True)
    damage_resistances_display = serializers.CharField()
    damage_resistances = DamageTypeSummarySerializer(many=True)
    damage_vulnerabilities_display = serializers.CharField()
    damage_vulnerabilities = DamageTypeSummarySerializer(many=True)
    condition_immunities_display = serializers.CharField()
    condition_immunities = ConditionSummarySerializer(many=True)

    class Meta:
        model = models.Creature
        fields = [
            'damage_immunities_display',
            'damage_immunities',
            'damage_resistances_display',
            'damage_resistances',
            'damage_vulnerabilities_display',
            'damage_vulnerabilities',
            'condition_immunities_display',
            'condition_immunities',
        ]


ABILITIES = [
    'strength', 'dexterity', 'constitution',
    'intelligence', 'wisdom', 'charisma',
]

SKILLS = [
    'acrobatics', 'animal_handling', 'arcana', 'athletics', 'deception',
    'history', 'insight', 'intimidation', 'investigation', 'medicine',
    'nature', 'perception', 'performance', 'persuasion', 'religion',
    'sleight_of_hand', 'stealth', 'survival',
]

# Default ability modifier for each skill check.
SKILL_DEFAULT_ABILITY = {
    'acrobatics': 'dexterity',
    'animal_handling': 'wisdom',
    'arcana': 'intelligence',
    'athletics': 'strength',
    'deception': 'charisma',
    'history': 'intelligence',
    'insight': 'wisdom',
    'intimidation': 'charisma',
    'investigation': 'intelligence',
    'medicine': 'wisdom',
    'nature': 'intelligence',
    'perception': 'wisdom',
    'performance': 'charisma',
    'persuasion': 'charisma',
    'religion': 'intelligence',
    'sleight_of_hand': 'dexterity',
    'stealth': 'dexterity',
    'survival': 'wisdom',
}


AbilityScoresSerializer = prefixed_aggregate_serializer(
    model=models.Creature, prefix='ability_score_', keys=ABILITIES,
    name='AbilityScores',
)

SavingThrowsSerializer = prefixed_aggregate_serializer(
    model=models.Creature, prefix='saving_throw_', keys=ABILITIES,
    name='SavingThrows',
)

SavingThrowsAllSerializer = prefixed_aggregate_serializer(
    model=models.Creature, prefix='saving_throw_', keys=ABILITIES,
    name='SavingThrowsAll',
    defaults_fn=lambda inst, key: getattr(inst, f'modifier_{key}'),
)

SkillBonusesSerializer = prefixed_aggregate_serializer(
    model=models.Creature, prefix='skill_bonus_', keys=SKILLS,
    name='SkillBonuses',
)

SkillBonusesAllSerializer = prefixed_aggregate_serializer(
    model=models.Creature, prefix='skill_bonus_', keys=SKILLS,
    name='SkillBonusesAll',
    defaults_fn=lambda inst, key: getattr(inst, f'modifier_{SKILL_DEFAULT_ABILITY[key]}'),
)


class CreatureSerializer(GameContentSerializer):
    '''The serializer for the Creature object.'''

    key = serializers.ReadOnlyField()
    ability_scores = AbilityScoresSerializer(source='*', read_only=True)
    modifiers = serializers.SerializerMethodField()
    saving_throws = SavingThrowsSerializer(source='*', read_only=True)
    saving_throws_all = SavingThrowsAllSerializer(source='*', read_only=True)
    skill_bonuses = SkillBonusesSerializer(source='*', read_only=True)
    skill_bonuses_all = SkillBonusesAllSerializer(source='*', read_only=True)
    resistances_and_immunities = CreatureResistancesAndImmunitiesSerializer(source='*')
    actions = CreatureActionSerializer(many=True)
    traits = CreatureTraitSerializer(many=True, read_only=True)
    speed = serializers.SerializerMethodField()
    speed_all = serializers.SerializerMethodField()
    experience_points = serializers.SerializerMethodField()
    document = DocumentSummarySerializer()
    type = CreatureTypeSummarySerializer()
    size = SizeSummarySerializer()
    languages = CreatureLanguageSerializer(source='*')
    environments = EnvironmentSummarySerializer(many=True)
    initiative_bonus = serializers.SerializerMethodField()
    illustration = ImageSummarySerializer()

    class Meta:
        '''Serializer meta options.'''
        model = models.Creature
        fields = [
            'key',
            'name',
            'document',
            'type',
            'size',
            'challenge_rating',
            'proficiency_bonus',
            'speed',
            'speed_all',
            'category',
            'subcategory',
            'alignment',
            'languages',
            'armor_class',
            'armor_detail',
            'hit_points',
            'hit_dice',
            'experience_points',
            'ability_scores',
            'modifiers',
            'initiative_bonus',
            'saving_throws',
            'saving_throws_all',
            'skill_bonuses',
            'skill_bonuses_all',
            'passive_perception',
            'resistances_and_immunities',
            'normal_sight_range',
            'darkvision_range',
            'blindsight_range',
            'tremorsense_range',
            'truesight_range',
            'actions',
            'traits',
            'creaturesets',
            'environments',
            'illustration'
        ]

    @extend_schema_field(inline_serializer(
        name="ability_modifiers",
        fields={
            # todo: technically they're all typed as any, but they're `floor`'d, so they should come out as integers
            "strength": serializers.IntegerField(),
            "dexterity": serializers.IntegerField(),
            "constitution": serializers.IntegerField(),
            "intelligence": serializers.IntegerField(),
            "wisdom": serializers.IntegerField(),
            "charisma": serializers.IntegerField(),
        })
    )
    def get_modifiers(self, creature):
        '''Modifiers helper method.'''
        return creature.get_modifiers()

    @extend_schema_field(inline_serializer(
        name="speed",
        fields={
            # todo: model typed as any
            "walk": serializers.StringRelatedField(),
            # todo: model typed as any
            "fly": serializers.StringRelatedField(),
            # todo: model typed as any
            "swim": serializers.StringRelatedField(),
            # todo: model typed as any
            "climb": serializers.StringRelatedField(),
            # todo: model typed as any
            "burrow": serializers.StringRelatedField(),
            # todo: and none
            "hover": serializers.BooleanField(),
        }
    ))
    def get_speed(self, creature):
        '''Explicit speed helper method.'''
        entries = creature.get_speed().items()
        return { key: value for key, value in entries if value is not None }

    @extend_schema_field(inline_serializer(
        name="speed_all",
        fields={
            # todo: model typed as any
            "unit": serializers.StringRelatedField(),
            "walk": serializers.IntegerField(),
            "crawl": serializers.IntegerField(),
            "hover": serializers.BooleanField(),
            "fly": serializers.IntegerField(allow_null=True),
            "burrow": serializers.IntegerField(allow_null=True),
            "climb": serializers.IntegerField(allow_null=True),
            "swim": serializers.IntegerField(allow_null=True),
        }
    ))
    def get_speed_all(self, creature):
        '''Implicit speed helper method.'''
        return creature.get_speed_all()

    # todo: model typed as any
    @extend_schema_field(OpenApiTypes.INT)
    def get_experience_points(self, creature):
        return creature.experience_points
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_initiative_bonus(self, creature):
        return creature.get_initiative_bonus()


class CreatureSetSerializer(GameContentSerializer):
    '''Serializer for the Creature Set object'''
    
    key = serializers.ReadOnlyField()
    creatures = CreatureSerializer(many=True, read_only=True, context={'request':{}})

    class Meta:
        '''Meta options for serializer.'''
        model = models.CreatureSet
        fields = '__all__'
