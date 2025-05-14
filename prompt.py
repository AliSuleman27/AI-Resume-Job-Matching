def generate_resume_prompt(resume_text):
    schema = """
**Instructions:**
- Parse the provided resume text and return the parsed data strictly in the JSON format as outlined in the schema below.
- Do not add any commentary or explanations; just return the structured JSON.
- If any data or field is missing, infer it where possible. For instance, if years of experience are not explicitly provided, calculate it based on the start and end dates of experience or education.
- If something cannot be inferred, leave the field as `null` or an empty string as appropriate.
- If there are multiple entries for a section (e.g., multiple jobs, educational qualifications, certifications), ensure each is captured in the order they appear in the resume.
- Handle edge cases where data may be incomplete or ambiguous, such as missing contact information, skills, or publications.
- If specific sections like publications, volunteer experiences, or awards are not present in the resume, leave them as empty lists.
- Follow the exact structure and data types as shown in the provided schema.

**Important Notes:**
- In the event of unclear or missing data (e.g., job responsibilities or skills), attempt to infer or leave it as null.
- The **contact info** should be filled based on provided details; if some fields (like email or phone) are missing, mark them as empty strings or `null`.
- Ensure all sections are accounted for logically based on the content provided in the resume. For example, if no projects are mentioned, leave the **projects** array empty.
- The **dates** should be formatted as `"YYYY-MM-DD"`. If the exact date is unknown, try to estimate or mark it as `null`.
- If there is no **summary** or brief description in the resume, the **summary** field should be marked as `null` or an empty string.

**Structured JSON Schema:**
"""
    
    json_schema = """
{
  "basic_info": {
    "full_name": "string",
    "current_title": "string",
    "gender": "string",
    "date_of_birth": "string",
    "nationality": "string"
  },
  "contact_info": {
    "email": "string",
    "phone": "string",
    "address": {
      "street": "string",
      "city": "string",
      "state": "string",
      "zip_code": "string",
      "country": "string"
    },
    "linkedin": "string",
    "github": "string",
    "portfolio": "string"
  },
  "summary": "string",
  "skills": [
    {
      "skill_name": "string",
      "proficiency": "string",
      "category": "string",
      "years_of_experience": "integer"
    }
  ],
  "education": [
    {
      "degree": "string",
      "field": "string",
      "institution": "string",
      "start_date": "string",
      "end_date": "string",
      "grade": "string",
      "location": "string",
      "courses": [
        "string"
      ]
    }
  ],
  "experience": [
    {
      "job_title": "string",
      "company": "string",
      "start_date": "string",
      "end_date": "string",
      "employment_type": "string",
      "location": "string",
      "responsibilities": [
        "string"
      ],
      "skills_used": [
        "string"
      ]
    }
  ],
  "projects": [
    {
      "title": "string",
      "description": "string",
      "technologies": [
        "string"
      ],
      "role": "string",
      "start_date": "string",
      "end_date": "string",
      "link": "string"
    }
  ],
  "certifications": [
    {
      "title": "string",
      "issuer": "string",
      "issue_date": "string",
      "expiration_date": "string",
      "credential_id": "string",
      "url": "string"
    }
  ],
  "publications": [
    {
      "title": "string",
      "journal": "string",
      "authors": [
        "string"
      ],
      "year": "integer",
      "doi": "string",
      "url": "string"
    }
  ],
  "languages": [
    {
      "language": "string",
      "proficiency": "string"
    }
  ],
  "interests": [
    "string"
  ],
  "volunteer_experience": [
    {
      "role": "string",
      "organization": "string",
      "start_date": "string",
      "end_date": "string",
      "description": "string"
    }
  ],
  "awards": [
    {
      "title": "string",
      "issuer": "string",
      "date": "string",
      "description": "string"
    }
  ],
  "links": [
    {
      "label": "string",
      "url": "string"
    }
  ]
}
"""

    return schema + f"\n\nResume Text: {resume_text}\n" + json_schema


def generate_job_prompt(job_description_text):
    schema = """
**Instructions:**
- Parse the provided job description text and return the structured data strictly in the JSON format as outlined in the schema below.
- Do not add any commentary or explanations; just return the structured JSON.
- If any data or field is missing or ambiguous, infer it where reasonable. For example, determine the job level or industry based on responsibilities or context clues.
- If something cannot be inferred, leave the field as `null`, an empty string, or an empty list as appropriate.
- If the job description includes multiple locations or skills, extract each of them appropriately.
- The `salary` field should be extracted if any compensation details are present (e.g., "100K/year", "50/hr", etc.).
- Ensure enum values (e.g., `employment_type`, `job_level`, `salary.period`, etc.) are selected from the listed options. If the value doesn't clearly match an enum, set it as `null`.
- Dates should be formatted as `"YYYY-MM-DD"` where applicable. If unknown, leave them as `null`.
- Make a reasonable attempt to differentiate between `responsibilities`, `requirements`, and `nice_to_have`. Use context like section headers ("You will be responsible for...", "Requirements", "Preferred", etc.) to guide you.
- If fields like `application_url`, `posting_date`, or `company.website` are not present, mark them as `null`.
- Set `analytics` fields (views and applications) to `0` if not specified.
- Set `metadata.created_at` and `metadata.updated_at` to the current date in `"YYYY-MM-DD"` format.
- Assume `metadata.source` as `"manual_post"` and `metadata.created_by_user_id` as a dummy UUID `"00000000-0000-0000-0000-000000000000"` unless otherwise available.

**Structured JSON Schema:**
"""

    json_schema = """
{
  "job_id": "string (UUID)",
  "title": "string",
  "description": "string",
  "summary": "string",
  "employment_type": "enum [\"full_time\", \"part_time\", \"contract\", \"temporary\", \"internship\", \"freelance\"]",
  "industry": "string",
  "department": "string",
  "function": "string",
  "job_level": "enum [\"entry\", \"mid\", \"senior\", \"lead\", \"manager\", \"director\", \"executive\"]",
  "locations": [
    {
      "city": "string",
      "state": "string",
      "country": "string",
      "zip_code": "string",
      "remote": "boolean"
    }
  ],
  "is_remote": "boolean",
  "is_hybrid": "boolean",
  "is_onsite": "boolean",
  "application_url": "string",
  "posting_date": "string",
  "closing_date": "string",
  "salary": {
    "currency": "string",
    "min": "number",
    "max": "number",
    "period": "enum [\"hour\", \"day\", \"week\", \"month\", \"year\"]",
    "is_estimated": "boolean"
  },
  "benefits": ["string"],
  "qualifications": {
    "education": [
      {
        "degree": "string",
        "field_of_study": "string",
        "level": "enum [\"high_school\", \"associate\", \"bachelor\", \"master\", \"phd\", \"other\"]"
      }
    ],
    "experience_years": {
      "min": "number",
      "max": "number"
    },
    "certifications": ["string"]
  },
  "skills": {
    "mandatory": ["string"],
    "optional": ["string"],
    "tools": ["string"]
  },
  "languages": [
    {
      "language": "string",
      "proficiency": "enum [\"basic\", \"conversational\", \"fluent\", \"native\"]"
    }
  ],
  "responsibilities": ["string"],
  "requirements": ["string"],
  "nice_to_have": ["string"],
  "company": {
    "name": "string",
    "website": "string",
    "description": "string"
  },
  "analytics": {
    "views": "integer",
    "applications": "integer"
  },
  "metadata": {
    "created_at": "string",
    "updated_at": "string",
    "created_by_user_id": "string",
    "source": "string"
  }
}
"""

    return schema + f"\n\nJob Description Text: {job_description_text}\n" + json_schema
