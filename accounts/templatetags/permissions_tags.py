from django import template
from accounts.permissions import user_is_admin

register = template.Library()


@register.filter
def is_admin(user):
    """
    Uso no template:
        {% load permissions_tags %}
        {% if request.user|is_admin %}
            ... coisas só de admin ...
        {% endif %}
    """
    return user_is_admin(user)
