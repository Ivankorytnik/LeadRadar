# LeadRadar AI
## Техническое задание v1.1

Дата: 01.10.2026  
Статус: базовая версия ТЗ для дальнейшей разработки

## 1. Цель продукта

LeadRadar AI - B2B SaaS и AI-приложение, которое по сайту компании или краткому описанию бизнеса автоматически понимает, что продает компания, кому это может быть нужно, формирует поисковые намерения и запросы, находит потенциальные заявки и закупочный спрос, проверяет актуальность, устраняет дубли, оценивает релевантность и помогает довести найденную возможность до контакта и CRM.

Основной сценарий:

**Сайт компании -> AI-профиль -> ICP -> поисковые намерения -> источники -> найденные возможности -> проверка -> скоринг -> ЛПР/контакты -> черновик обращения -> CRM -> аналитика результата -> обучение системы.**

## 2. Основные пользователи

- собственники и руководители малого и среднего бизнеса;
- B2B отделы продаж;
- business development;
- тендерные отделы;
- производители и поставщики;
- сервисные компании;
- агентства, работающие с лидогенерацией;
- отраслевые команды продаж.

## 3. Базовый функционал MVP

Сохраняется уже реализованный функционал:

- регистрация компании и пользователя;
- анализ сайта компании;
- автоматическое создание Search Profile;
- ручное редактирование Search Profile;
- генератор поисковых запросов;
- Yandex Search API connector;
- SerpAPI-compatible connector;
- web crawler;
- нормализация результатов;
- heuristic и AI-анализ;
- relevance score 0-100;
- антидубли;
- проверка актуальности;
- Opportunity database;
- dashboard;
- статусы Opportunity;
- email delivery;
- Telegram delivery;
- webhook API;
- HMAC подпись;
- retry queue;
- delivery log;
- REST API;
- API key;
- XLSX export;
- scheduler;
- admin view;
- demo mode.

## 4. Новая продуктовая модель

LeadRadar должен развиваться не только как отдельный Web SaaS, но и как единое поисковое ядро, доступное из разных AI-платформ.

Архитектурный принцип:

**LeadRadar Core -> API/MCP -> платформенные адаптеры -> ChatGPT / Claude / Grok / Web SaaS / Telegram / внешние CRM.**

Бизнес-логика, поиск, скоринг, дедупликация, история и аналитика должны находиться в одном backend. Платформенные приложения не должны дублировать ядро.

## 5. MCP слой

Добавить отдельный MCP server LeadRadar.

Минимальный набор MCP actions:

- analyze_company;
- create_search_profile;
- get_search_profile;
- update_search_profile;
- generate_search_intents;
- generate_search_queries;
- run_search;
- get_opportunities;
- get_opportunity;
- qualify_opportunity;
- reject_opportunity;
- find_decision_makers;
- generate_outreach_draft;
- push_to_crm;
- update_opportunity_status;
- get_analytics;
- get_win_loss_analytics.

MCP должен использовать авторизацию конкретной организации и tenant isolation.

## 6. AI-платформы

### 6.1 ChatGPT

Предусмотреть отдельное приложение LeadRadar для ChatGPT через Apps SDK + MCP.

Примеры запросов:

- "Проанализируй мой сайт и найди потенциальных клиентов".
- "Найди компании в Германии, которым может понадобиться наша услуга".
- "Покажи новые возможности с релевантностью выше 75%".
- "Подготовь первое письмо по этим 20 лидам".
- "Добавь выбранные лиды в CRM".

Интерфейс внутри ChatGPT должен поддерживать карточки найденных возможностей, фильтры, подтверждение действий и переход в Web Control Center LeadRadar.

### 6.2 Claude

Предусмотреть Claude Skill + MCP connector.

Skill должен описывать:
- методику анализа бизнеса;
- построение ICP;
- правила формирования search intent;
- правила проверки источников;
- правила скоринга;
- правила подготовки outreach;
- критерии качества результата.

### 6.3 Grok

Предусмотреть:
- Grok Build plugin;
- Grok Bot для сценария outbound prospecting;
- MCP integration;
- skills и команды поиска.

## 7. AI Company Profiler

После ввода URL система должна автоматически определять:

- компанию;
- продукты и услуги;
- отрасли;
- географию;
- B2B/B2C/B2G модель;
- типовых покупателей;
- основные use cases;
- боли клиента;
- признаки закупочного намерения;
- ключевые слова;
- синонимы;
- отраслевую лексику;
- исключающие запросы;
- возможных конкурентов;
- потенциальные каналы поиска.

Результат сохраняется как Company Intelligence Profile.

## 8. ICP Builder

Добавить отдельную сущность ICP Profile.

Поля:

- отрасль;
- размер компании;
- география;
- должности ЛПР;
- тип потребности;
- триггеры покупки;
- примерный бюджет;
- срочность;
- стоп-факторы;
- negative ICP;
- preferred sources;
- languages.

Для одной организации должно быть возможно создать несколько ICP.

## 9. Intent Engine

Поиск должен идти не только по ключевым словам, но и по намерению.

Категории intent:

- хочу купить;
- ищу поставщика;
- ищу подрядчика;
- нужен исполнитель;
- запрос КП;
- тендер;
- запрос цены;
- нужен аналог;
- ищем партнера;
- замена текущего поставщика;
- проблема, которую решает продукт клиента;
- запуск нового объекта;
- расширение бизнеса;
- найм как косвенный сигнал;
- инвестиции как косвенный сигнал;
- изменение продукта или инфраструктуры;
- негативный отзыв о текущем поставщике.

Intent Engine формирует сотни комбинаций поисковых формулировок, но хранит связь каждого запроса с конкретным intent.

## 10. Источники

Архитектура должна поддерживать подключаемые Connector.

Категории:

- поисковые системы;
- сайты компаний;
- доски объявлений;
- тендерные площадки;
- государственные закупки;
- отраслевые каталоги;
- публичные соцсети;
- Telegram;
- MAX;
- Reddit;
- форумы;
- вакансии;
- новости;
- корпоративные пресс-релизы;
- публичные базы;
- API партнеров.

Каждый результат должен сохранять источник, URL, дату обнаружения, дату публикации, evidence и время последней проверки.

## 11. Opportunity Intelligence

Каждая Opportunity должна содержать не только текст источника, но и структурированный AI-анализ:

- краткое описание;
- что требуется;
- почему подходит клиенту LeadRadar;
- intent;
- buyer type;
- location;
- urgency;
- estimated deal value, если возможно;
- relevance score;
- confidence;
- evidence;
- дата;
- источник;
- возможный ЛПР;
- следующий рекомендуемый шаг.

## 12. Evidence First

Любой AI-вывод по возможности должен иметь evidence.

Нельзя показывать пользователю:
- неподтвержденный телефон как достоверный;
- выдуманное имя ЛПР;
- выдуманный бюджет;
- выдуманный срок;
- выдуманную компанию.

В карточке должна быть отдельная секция "Почему система считает это лидом".

## 13. Расширенный скоринг

Итоговый score формируется из отдельных факторов:

- intent score;
- ICP fit;
- service fit;
- geography fit;
- freshness;
- urgency;
- source confidence;
- contactability;
- deal potential;
- duplicate risk;
- negative signals.

Пользователь должен иметь возможность изменить веса скоринга.

## 14. Decision Maker Finder

Для квалифицированной возможности система пытается найти:

- компанию;
- сайт;
- имя ЛПР;
- должность;
- публичный рабочий email;
- публичный телефон;
- LinkedIn или иной публичный профиль;
- доказательство связи контакта с компанией.

Контакт не должен считаться подтвержденным без источника.

## 15. Outreach Copilot

По квалифицированному лиду система создает:

- короткое первое сообщение;
- email;
- LinkedIn/соцсеть сообщение;
- follow-up;
- call opener;
- краткое value proposition.

Текст должен использовать evidence из найденной возможности.

По умолчанию LeadRadar не отправляет внешнее сообщение автоматически.

Перед отправкой требуется явное подтверждение пользователя.

## 16. CRM Actions

Добавить connector layer для CRM.

Приоритет интеграций:

- HubSpot;
- Salesforce;
- Pipedrive;
- Bitrix24;
- amoCRM;
- webhook;
- REST API.

Действия:

- создать Lead;
- создать Company;
- создать Contact;
- добавить источник;
- добавить evidence;
- записать relevance score;
- создать задачу;
- сохранить outreach draft;
- обновить статус.

## 17. Win/Loss Learning

Добавить обязательный контур обратной связи.

Пользователь должен указывать результат:

- неинтересно;
- нерелевантно;
- дубль;
- неактуально;
- связались;
- ответил;
- встреча;
- КП;
- переговоры;
- выиграно;
- проиграно.

Система должна анализировать результаты и со временем улучшать:

- ICP;
- поисковые намерения;
- запросы;
- источники;
- веса скоринга;
- типы lead signals.

Обучение не должно автоматически менять production Search Profile без сохранения версии и возможности отката.

## 18. Analytics of Wins

Добавить отдельный экран "Победы".

Метрики:

- найдено возможностей;
- квалифицировано;
- передано в CRM;
- контактов найдено;
- сообщений подготовлено;
- ответов;
- встреч;
- КП;
- выигранных сделок;
- проигранных сделок;
- conversion by source;
- conversion by intent;
- conversion by ICP;
- conversion by query;
- conversion by country;
- conversion by industry;
- revenue influenced;
- cost per qualified opportunity;
- cost per win.

Главная задача аналитики - показать, какие источники и типы намерений реально приводят к продажам.

## 19. Vertical Packs

Архитектура должна поддерживать готовые отраслевые пакеты.

Vertical Pack содержит:

- ICP templates;
- intent library;
- query library;
- source library;
- scoring presets;
- negative keywords;
- outreach templates;
- отраслевой словарь.

Первые возможные vertical packs:

- construction;
- logistics;
- fleet;
- waste management;
- heavy equipment;
- industrial services;
- SaaS;
- agencies.

Пакет не должен быть отдельным продуктом. Он подключается к общему LeadRadar Core.

## 20. Международный режим

Предусмотреть:

- country;
- region;
- city;
- search language;
- interface language;
- source language;
- timezone;
- currency;
- multilingual query generation;
- multilingual opportunity normalization;
- локальные источники;
- отдельные правила compliance по странам.

## 21. Human Approval

Все действия, которые меняют внешние системы или отправляют сообщения, должны иметь режим подтверждения.

Минимальные уровни:

- READ;
- PREPARE;
- CONFIRM;
- AUTO.

По умолчанию новые интеграции работают в CONFIRM.

AUTO можно включить отдельно для конкретных безопасных действий.

## 22. Web Control Center

Личный кабинет должен стать центральным местом управления.

Разделы:

- Dashboard;
- Opportunities;
- Search Profiles;
- ICP;
- Intents;
- Sources;
- Contacts;
- Outreach;
- CRM Integrations;
- AI Apps;
- Analytics;
- Wins;
- Billing;
- API;
- Settings;
- Admin.

Пользователь должен иметь возможность управлять поиском и интеграциями без изменения кода.

## 23. Multi-tenant architecture

Обязательные требования:

- tenant_id для всех пользовательских бизнес-сущностей;
- RBAC;
- изоляция данных;
- audit log;
- секреты только на backend;
- API rate limits;
- encrypted credentials;
- idempotency;
- retry;
- versioning Search Profile;
- staging/production configuration;
- backup.

## 24. Основные сущности

- Organization;
- User;
- Membership;
- CompanyIntelligenceProfile;
- ICPProfile;
- SearchProfile;
- SearchIntent;
- SearchQuery;
- SourceConnector;
- SearchRun;
- RawResult;
- Opportunity;
- OpportunityEvidence;
- Company;
- Contact;
- DecisionMaker;
- OutreachDraft;
- CRMAction;
- Delivery;
- WinLossOutcome;
- LearningSignal;
- PlatformAdapter;
- ConnectorCredential;
- AuditEvent.

## 25. API First

Все функции ядра должны быть доступны не только UI, но и через API.

Это необходимо для:
- AI-платформ;
- партнеров;
- CRM;
- Telegram;
- автоматизаций;
- White Label;
- внешних агентов.

## 26. Монетизация

Поддержать:

- Free / Trial;
- подписку по тарифу;
- лимит поисков;
- лимит найденных возможностей;
- лимит AI enrichment;
- платные дополнительные источники;
- платные vertical packs;
- API тариф;
- Team тариф;
- Agency тариф;
- Enterprise;
- premium integrations.

Монетизация AI-платформ не должна быть единственным источником выручки. Основной billing хранится в LeadRadar, а ChatGPT, Claude и Grok рассматриваются как каналы привлечения, использования и дистрибуции.

## 27. Product Metrics

Обязательные продуктовые KPI:

- activation rate;
- time to first relevant opportunity;
- relevant opportunities per search run;
- accepted opportunity rate;
- false positive rate;
- duplicate rate;
- freshness rate;
- CRM push rate;
- meeting rate;
- win rate;
- revenue influenced;
- retention;
- search cost per organization;
- AI cost per qualified opportunity.

## 28. Ключевой принцип

LeadRadar не должен быть просто поисковиком ссылок.

Целевой продукт:

**"Дай LeadRadar сайт компании, и система найдет людей и компании, которым сейчас может быть нужно то, что эта компания продает, объяснит почему, поможет найти ЛПР и довести возможность до CRM".**

## 29. Приоритет разработки после MVP

### P1
- Company Intelligence Profile;
- ICP Builder;
- Intent Engine;
- улучшенный Opportunity Intelligence;
- evidence;
- расширенный scoring;
- Win/Loss feedback;
- Analytics of Wins.

### P2
- MCP server;
- ChatGPT app;
- Claude Skill;
- Grok plugin/bot;
- CRM connectors;
- Decision Maker Finder;
- Outreach Copilot.

### P3
- Vertical Packs;
- international source packs;
- advanced billing;
- team workflows;
- agency mode;
- enterprise deployment.

## 30. Ограничение архитектуры

Нельзя создавать отдельные независимые backend для ChatGPT, Claude, Grok, Telegram и Web.

Единым источником истины является LeadRadar Core.

Все платформы используют общие:
- организации;
- Search Profiles;
- ICP;
- результаты;
- скоринг;
- историю;
- billing;
- analytics;
- audit log.
