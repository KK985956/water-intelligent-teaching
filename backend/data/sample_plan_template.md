# {{ course_name }}教学方案

## 一、课程信息
- 模板名称：{{ template_name }}
- 课程类型：{{ course_type_label }}
- 授课对象：{{ audience }}
- 课时安排：{{ hours }} 课时
- 生成时间：{{ generated_at }}

## 二、教学目标
{% for goal in goals %}
- {{ goal }}
{% endfor %}

## 三、教学重难点
- 教学重点：{{ focus_points | join("；") }}
- 教学难点：{{ difficult_points | join("；") }}

## 四、教学流程
{% for section in outline %}
### {{ loop.index }}. {{ section.title }}（{{ section.duration }}）
- 教学内容：{{ section.content }}
- 教学方法：{{ section.method }}
- 知识点：{{ section.knowledge_points | join("；") }}
{% endfor %}

## 五、案例与练习
{% for item in cases %}
- 案例：{{ item }}
{% endfor %}
{% for item in exercises %}
- 练习：{{ item }}
{% endfor %}

## 六、课后任务
{% for item in homework %}
- {{ item }}
{% endfor %}

## 七、教学总结
{{ summary }}
