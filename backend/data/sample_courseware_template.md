# {{ course_name }}课件模板

## 封面页
- 标题：{{ course_name }}
- 模板：{{ theme_name }}

## 内容页
{% for slide in slides %}
### {{ loop.index }}. {{ slide.title }}
{% for bullet in slide.bullets %}
- {{ bullet }}
{% endfor %}
{% endfor %}
