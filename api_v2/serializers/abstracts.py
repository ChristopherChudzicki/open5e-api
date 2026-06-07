"""Abstract serializers."""
from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers


# Base for serializers produced by `prefixed_aggregate_serializer`. Filters
# null entries (or substitutes defaults via `_defaults_fn`) at serialization
# time. Not meant to be subclassed directly — docstring intentionally absent
# so drf-spectacular doesn't apply it as the schema description.
class _AggregateSerializerBase(serializers.Serializer):

    # Override on the generated subclass: (instance, key) -> value, called
    # only when the underlying model field is None. Leaving as None means
    # "drop null keys from the output" (the "explicit" variant).
    _defaults_fn = None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self._defaults_fn is None:
            return {k: v for k, v in data.items() if v is not None}
        fn = self._defaults_fn
        return {k: (fn(instance, k) if v is None else v) for k, v in data.items()}


def prefixed_aggregate_serializer(*, model, prefix, keys, name, defaults_fn=None):
    """
    Build a Serializer class that exposes `{<key>: model.<prefix><key>}` for
    each key, with per-field metadata (allow_null, required, help_text)
    introspected from the underlying model field via `model._meta.get_field`.

    Without `defaults_fn`, keys whose source field is None are omitted from the
    output. With `defaults_fn` (an `(instance, key) -> value` callable), those
    keys are populated from the callable instead — the "_all" variant pattern.

    Apply as a nested field on the parent serializer with `source='*'`:

        ABILITIES = ['strength', 'dexterity', ...]
        SavingThrows = prefixed_aggregate_serializer(
            model=Creature, prefix='saving_throw_', keys=ABILITIES,
            name='SavingThrows',
        )

        class CreatureSerializer(GameContentSerializer):
            saving_throws = SavingThrows(source='*', read_only=True)

    All fields are emitted as IntegerField; broaden the dispatch here if a
    caller needs non-integer aggregates.
    """
    attrs = {}
    for key in keys:
        mf = model._meta.get_field(f'{prefix}{key}')
        attrs[key] = serializers.IntegerField(
            source=f'{prefix}{key}',
            allow_null=mf.null,
            required=not (mf.null or mf.blank),
            help_text=mf.help_text or '',
        )
    if defaults_fn is not None:
        attrs['_defaults_fn'] = staticmethod(defaults_fn)
    return type(name, (_AggregateSerializerBase,), attrs)


class _CrossReferenceLinkSerializer(serializers.Serializer):
    """One link in crossreferences.to; defines API shape and serialization."""

    anchor = serializers.CharField()
    url = serializers.URLField()


# OpenAPI schema for crossreferences: { "to": [{ anchor, url }] }
_crossreferences_schema = inline_serializer(
    name="CrossReferences",
    fields={
        "to": _CrossReferenceLinkSerializer(many=True),
    },
)


class GameContentSerializer(serializers.ModelSerializer):  

    """
    Much of the logic included in the GameContentSerializer is intended to 
    support manipulating data returned by the serializer via query parameters.
    """
    
    def remove_unwanted_fields(self, dynamic_params):
        """
        Takes the value of the 'fields', a string of comma-separated values, 
        and removes all fields not in this list from the serializer
        """
        if fields_to_keep := dynamic_params.pop("fields", None):
            fields_to_keep = set(fields_to_keep.split(","))
            all_fields = set(self.fields.keys())
            for field in all_fields - fields_to_keep:
                self.fields.pop(field, None)

    def get_or_create_dynamic_params(self, child):
        """
        Creates dynamic params on the serializer context if it doesn't already
        exist, then returns the dynamic parameters
        """
        if "dynamic_params" not in self.fields[child]._context:
            self.fields[child]._context.update({"dynamic_params": {}})
        return self.fields[child]._context["dynamic_params"]

    @staticmethod
    def split_param(dynamic_param):
        """
        Splits a dynamic parameter into its target child serializer and value.
        Returns the values as a tuple.
        eg. 
            'document__fields=name' -> ('document', 'fields=name')
            'document__gamesystem__fields=name' -> ('document', 'gamesystem__fields=name')
        """
        crumbs = dynamic_param.split("__")
        return crumbs[0], "__".join(crumbs[1:]) if len(crumbs) > 1 else None

    def set_dynamic_params_for_children(self, dynamic_params):
        """
        Passes nested dynamic params to child serializer.
        eg. the param 'document__fields=name'
        """
        for param, fields in dynamic_params.items():
            child, child_dynamic_param = self.split_param(param)
            if child in self.fields.keys():
                # Get dynamic parameters for child serializer and update
                child_dynamic_params = self.get_or_create_dynamic_params(child)
                child_dynamic_params.update({child_dynamic_param: fields})

                # Overwrite existing params to remove 'fields' inherited from parent serializer
                self.fields[child]._context['dynamic_params'] = {
                    **child_dynamic_params,
                }

    @staticmethod
    def is_param_dynamic(p):
        """
        Returns true if parameter 'p' is a dynamic parameter. Currently the 
        only dynamic param supported is 'fields', so we check for that
        """
        return p.endswith("fields")

    def get_dynamic_params_for_root(self, request):
        """
        Returns a dict of dynamic query parameters extracted from the 'request'
        object. Only works on the root serializer (child serializers do no 
        include a 'request' field)
        """
        query_params = request.query_params.items()
        return {k: v for k, v in query_params if self.is_param_dynamic(k)}

    def _is_root_or_list_item_serializer(self):
        """True if this serializer is the root or a top-level list item (not nested)."""
        if self.parent is None:
            return True
        if isinstance(self.parent, serializers.ListSerializer):
            # Only treat as "list item" when the list itself is the root (e.g. list view)
            return self.parent.parent is None
        return False

    def get_dynamic_params(self):
        """
        Returns dynamic parameters stored on the serializer context
        """
        # The context for ListSerializers is stored on the parent
        if isinstance(self.parent, serializers.ListSerializer):
            return self.parent._context.get("dynamic_params", {})
        return self._context.get("dynamic_params", {})

    def get_fields(self):
        """Add crossreferences only for root or list-item serializers (not nested)."""
        fields = super().get_fields()
        if self._is_root_or_list_item_serializer():
            fields["crossreferences"] = serializers.SerializerMethodField()
        return fields

    @extend_schema_field(_crossreferences_schema)
    def get_crossreferences(self, obj):
        """Return crossreferences for API output; None for non-sources. Uses obj.crossreferences (prefetch-friendly)."""
        if not (hasattr(obj, "is_crossreference_source") and obj.is_crossreference_source()):
            return None
        request = self.context.get("request")
        to_links = [
            {"anchor": cr.anchor, "url": cr.reference_api_url(request)}
            for cr in obj.crossreferences.all()
        ]
        return {
            "to": _CrossReferenceLinkSerializer(instance=to_links, many=True).data,
        }

    def __init__(self, *args, **kwargs):
        request = kwargs.get("context", {}).get("request")
        super().__init__(*args, **kwargs)

        # Request is only present on root serializer
        if request:
            dynamic_params = self.get_dynamic_params_for_root(request)
            self._context.update({"dynamic_params": dynamic_params})

    def to_representation(self, instance):
        # if dynamic params are present, rmv requested fields and pass params 
        # to child serializers
        if dynamic_params := self.get_dynamic_params().copy():
            self.remove_unwanted_fields(dynamic_params)
            self.set_dynamic_params_for_children(dynamic_params)
        data = super().to_representation(instance)
        # Omit crossreferences key when null so non-sources (e.g. Document) have no key
        return {
            k: v for k, v in data.items()
            if not (k == "crossreferences" and v is None)
        }

    class Meta:
        abstract = True


class DescriptionSerializer(serializers.ModelSerializer):
    gamesystem = serializers.SerializerMethodField()
    class Meta:
        model = None
        abstract = True

    def get_gamesystem(self,obj):
        return obj.document.gamesystem.key
