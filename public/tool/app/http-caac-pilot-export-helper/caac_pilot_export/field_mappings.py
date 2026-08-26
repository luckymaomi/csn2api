from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecordSpec:
    label: str
    fields: dict[str, str]


TOP_LEVEL_FIELD_LABELS = {
    "pilotId": "飞行员ID",
    "pilotname": "姓名",
    "pilotnameeng": "姓名拼音",
    "pilotPhotoFileUrl": "照片文件URL",
    "pilotIdFileUrl": "身份证明文件URL",
    "pilotDegreeFileUrl": "学历证明文件URL",
    "country": "国籍",
    "birthday": "出生日期",
    "medicalBirthday": "体检信息出生日期",
    "sex": "性别",
    "birthplace": "出生地",
    "nation": "民族",
    "mobile": "手机号码",
    "mailaddr": "通讯地址",
    "zipcode": "邮政编码",
    "chineseOrg": "工作单位",
    "address": "永久住址",
    "idType": "身份证明名称",
    "idCode": "身份证明编号",
    "archiveNo": "档案号",
    "regionName": "所属地区",
    "licenseNo": "执照编号",
    "licenseTypeName": "所持执照",
    "nameCn": "所持执照",
    "licenseStatus": "执照状态",
    "englishLevel": "英语语言等级",
    "validDate": "英语语言等级有效期",
    "chineseLevel": "汉语语言等级",
    "chineseLevelValidDate": "汉语语言等级有效期",
    "licenseLimit": "执照备注原文",
    "degree": "学历",
    "medicalno": "体检合格证编号",
    "expDate": "执照有效期",
    "enddate": "体检合格证有效期",
    "copType": "副驾驶类别",
    "pilotgrade": "飞行员等级",
}

LICENSE_REMARK_LABELS = {
    "englishLevel": "英语语言能力",
    "chineseLevel": "汉语语言能力",
    "validDate": "有效期至",
    "chineseLevelValidDate": "有效期至",
    "qualification": "无线电通信资格",
}

TREE_FIELD_LABELS = {
    "layerinfo": "执照等级",
    "layerId": "等级ID",
    "limitEnglish": "英语限制",
    "limitZN": "中文限制",
    "limitEN": "英文限制",
}

COMMON_RECORD_FIELDS = {
    "pilotId": "飞行员ID",
    "eindex": "排序序号",
    "creationBy": "创建人",
    "creationDate": "创建时间",
    "updateBy": "更新人",
    "updateDate": "更新时间",
    "validFlag": "有效标志",
}

RECORD_SPECS = {
    "educationList": RecordSpec(
        "学习简历",
        {
            "startDate": "开始日期",
            "endDate": "结束日期",
            "school": "学校",
            "college": "院系",
            "major": "专业",
            "degree": "学历或学位",
            "eduId": "学习简历ID",
            "note": "备注",
            **COMMON_RECORD_FIELDS,
        },
    ),
    "workexps": RecordSpec(
        "工作经历",
        {
            "startDate": "开始日期",
            "endDate": "结束日期",
            "location": "工作地点",
            "organization": "工作单位",
            "title": "职务",
            "workExpId": "工作经历ID",
            "note": "备注",
            **COMMON_RECORD_FIELDS,
        },
    ),
    "jzhxinfos": RecordSpec(
        "机长航线",
        {
            "CHECKLINE": "检查航段",
            "CHECKPLACE": "检查地点",
            "EXAMINER": "检查员",
            "CHECKDATE": "检查日期",
            "LASTEXPDATE": "到期日期",
            "RESULT": "检查状态",
            "CHECK_ID": "检查记录ID",
        },
    ),
    "yjscinfos": RecordSpec(
        "应急生存",
        {
            "CHECKPLACE": "训练地点",
            "CHECKDATE": "训练日期",
            "LASTEXPDATE": "到期日期",
            "RESULT": "检查状态",
            "CHECKLINE": "检查航段",
            "EXAMINER": "检查员",
            "CHECK_ID": "检查记录ID",
        },
    ),
    "printhis": RecordSpec(
        "正式执照打印历史",
        {
            "PRINTDATE": "打印日期",
            "USERNAME": "打印人",
            "PRINTREASON": "打印原因",
        },
    ),
    "printList": RecordSpec(
        "正式执照打印情况",
        {
            "agreeDate": "同意日期",
            "printReason": "打印原因",
            "agreeUser": "同意人",
            "appId": "申请ID",
            "cardId": "卡片ID",
            "cardNo": "卡号",
            "licenseId": "执照ID",
            "notes": "备注",
            "printDate": "打印日期",
            "printId": "打印记录ID",
            "printStatus": "打印状态",
            "printUser": "打印人",
            "receiveFlag": "领取标志",
            "validDate": "有效日期",
            "validUser": "生效人",
            **COMMON_RECORD_FIELDS,
        },
    ),
    "checkpcinfos": RecordSpec(
        "熟练检查",
        {
            "CHECKDATE": "检查日期",
            "CHECKTYPE": "检查类型",
            "ACMODEL": "航空器型号",
            "EXAMINER": "考试员",
            "NOTES": "备注",
            "ACMODELID": "航空器型号ID",
            "BASEMONTH": "基准月",
            "LASTEXPDATE": "到期日期",
            "NEXTDATE": "下次检查日期",
            "NEXTEXPDATE": "下次到期日期",
            "NEXT_MONTH": "下次检查月份",
            "RESULT": "检查状态",
            "PCID": "熟练检查ID",
        },
    ),
}
