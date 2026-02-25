from __future__ import annotations

from functools import lru_cache

from django.apps import apps
from django.db import transaction
from django.db.models import FileField
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .media_utils import is_absolute_media_reference, normalize_media_file_name

_REPLACED_FILES_ATTR = "_cleanup_replaced_files"
_DELETED_FILES_ATTR = "_cleanup_deleted_files"


@lru_cache(maxsize=None)
def _model_file_field_names(model) -> tuple[str, ...]:
    return tuple(field.name for field in model._meta.fields if isinstance(field, FileField))


@lru_cache(maxsize=1)
def _all_file_fields() -> tuple[tuple[type, str], ...]:
    rows: list[tuple[type, str]] = []
    for model in apps.get_models():
        for field_name in _model_file_field_names(model):
            rows.append((model, field_name))
    return tuple(rows)


def _is_referenced_anywhere(name: str) -> bool:
    if not name:
        return False
    for model, field_name in _all_file_fields():
        lookup = {field_name: name}
        if model._default_manager.filter(**lookup).exists():
            return True
    return False


def _queue_delete_if_unreferenced(storage, name: str) -> None:
    normalized_name = normalize_media_file_name(name)
    if not normalized_name or is_absolute_media_reference(normalized_name):
        return

    def _delete():
        if _is_referenced_anywhere(normalized_name):
            return
        storage.delete(normalized_name)

    transaction.on_commit(_delete)


@receiver(pre_save)
def _collect_replaced_files(sender, instance, **kwargs):
    field_names = _model_file_field_names(sender)
    if not field_names:
        return
    if not getattr(instance, "pk", None) or getattr(instance._state, "adding", False):
        return

    previous = sender._default_manager.filter(pk=instance.pk).only(*field_names).first()
    if not previous:
        return

    pending: list[tuple[object, str]] = []
    for field_name in field_names:
        old_file = getattr(previous, field_name, None)
        new_file = getattr(instance, field_name, None)

        old_name = normalize_media_file_name(getattr(old_file, "name", ""))
        new_name = normalize_media_file_name(getattr(new_file, "name", ""))
        if not old_name or old_name == new_name:
            continue
        if is_absolute_media_reference(old_name):
            continue

        storage = getattr(old_file, "storage", None)
        if storage:
            pending.append((storage, old_name))

    setattr(instance, _REPLACED_FILES_ATTR, pending)


@receiver(post_save)
def _delete_replaced_files(sender, instance, **kwargs):
    pending: list[tuple[object, str]] = getattr(instance, _REPLACED_FILES_ATTR, [])
    if hasattr(instance, _REPLACED_FILES_ATTR):
        delattr(instance, _REPLACED_FILES_ATTR)

    for storage, name in pending:
        _queue_delete_if_unreferenced(storage, name)


@receiver(pre_delete)
def _collect_deleted_files(sender, instance, **kwargs):
    field_names = _model_file_field_names(sender)
    if not field_names:
        return

    pending: list[tuple[object, str]] = []
    for field_name in field_names:
        file_obj = getattr(instance, field_name, None)
        file_name = normalize_media_file_name(getattr(file_obj, "name", ""))
        if not file_name or is_absolute_media_reference(file_name):
            continue
        storage = getattr(file_obj, "storage", None)
        if storage:
            pending.append((storage, file_name))

    setattr(instance, _DELETED_FILES_ATTR, pending)


@receiver(post_delete)
def _delete_deleted_files(sender, instance, **kwargs):
    pending: list[tuple[object, str]] = getattr(instance, _DELETED_FILES_ATTR, [])
    if hasattr(instance, _DELETED_FILES_ATTR):
        delattr(instance, _DELETED_FILES_ATTR)

    for storage, name in pending:
        _queue_delete_if_unreferenced(storage, name)
