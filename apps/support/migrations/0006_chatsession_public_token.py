import secrets

from django.db import migrations, models


def _generate_token() -> str:
    return secrets.token_urlsafe(24)


def populate_public_tokens(apps, schema_editor):
    ChatSession = apps.get_model('support', 'ChatSession')
    db_alias = schema_editor.connection.alias

    for session in ChatSession.objects.using(db_alias).all().only('id', 'public_token'):
        token = (session.public_token or '').strip()
        if token:
            continue
        token = _generate_token()
        while ChatSession.objects.using(db_alias).filter(public_token=token).exists():
            token = _generate_token()
        session.public_token = token
        session.save(update_fields=['public_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0005_alter_chatmessage_options_alter_chatsession_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatsession',
            name='public_token',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.RunPython(populate_public_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='chatsession',
            name='public_token',
            field=models.CharField(db_index=True, editable=False, max_length=64, unique=True),
        ),
    ]
