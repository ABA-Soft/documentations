> **TL;DR:** Ez a dokumentum egy .NET backend nyelvvizsga rendszer (FIDE) architektúrális problémáit és azok megoldásait tartalmazza. Ha először olvasod, kezdd a "Gyors áttekintés" szekcióval, majd ugorj arra a problémára, ami a legsürgetőbb.

## 📌 Gyors Áttekintés

**Mi ez a rendszer?**
Egy nyelvvizsga feladatbank, ahol:

- **ItemWriter-ek** feladatokat írnak (pl. reading comprehension, listening)
- **Translator-ök** fordítják más nyelvekre (angol → német/francia/stb.)
- **Reviewer-ek** ellenőrzik a minőséget
- **Institute-ok** vizsgákat rendelnek
- **Examiner-ek** vizsgáztatnak

**Legnagyobb problémák (prioritás szerint):**

1. 🔴 **KRITIKUS - Security hole:** Bárki szerkesztheti más feladatát (hiányzik resource-based authorization)
2. 🔴 **KRITIKUS - Performance:** Minden művelet lassú (500ms+), mert KeyCloak API-t hívogatjuk
3. 🟠 **NAGY - Karbantarthatóság:** 78 osztályos monolith modulok, duplikált kód mindenhol
4. 🟡 **KÖZEPES - Domain model:** Üzleti logika nem egyértelmű (pl. TaskGroup nem létezik explicit)

**Mit nyersz a refaktorral?**

- ✅ **Biztonság:** Senki nem férhet hozzá más feladatához
- ✅ **Sebesség:** 10x gyorsabb (50ms helyett 500ms)
- ✅ **Karbantarthatóság:** Kisebb, átlátható modulok
- ✅ **Fejlesztési sebesség:** Új feature-ök gyorsabban implementálhatók

---

## Projekt Kontextus

**Domain:** Nyelvvizsga feladatbank rendszer (Test Item Development)  
**Tech Stack:** .NET 8, EF Core, MediatR (CQRS), KeyCloak (Identity Provider)  
**Alkalmazott minták:** Repository Pattern, CQRS, Domain Events (részben)  
**Team méret:** [adj hozzá, ha releváns]  
**Production load:** [adj hozzá, ha releváns]

### Domain Hierarchia (Egyszerűen)

Képzeld el úgy, mint egy könyv struktúrát:

```
📚 Context (Domain): "Orvosi téma"
    ↓
    📖 Situation (ActionField): "Orvosi vizit"
        ↓
        📄 DetailedScenario: "Páciensnek fáj a foga"
            ↓
            🌐 TaskGroup: Ez a feladat ÖSSZES nyelven (angol, német, francia)
                ↓
                📝 Task: EGY konkrét nyelvi verzió (pl. a német verzió)
                    ↓
                    ✏️ Field: A feladat elemei (kérdés, válaszlehetőségek, képek)
                        ↓
                        📋 Item: Konkrét kérdések, válaszok
```

**Példa életciklus:**

1. ItemWriter létrehoz egy feladatot **angol** nyelven (Task)
2. Feladatot review-olják → OK
3. TestDeveloper indít egy **fordítást német** nyelvre
4. Translator lefordítja → új **Task** entity jön létre (német)
5. Mindkét Task (angol + német) ugyanabban a **TaskGroup**-ban van
6. Ha minden nyelv kész → TaskGroup "Published" státuszba kerül

### User Típusok (egyszerűen)

Minden user egy **BaseUserEntity** (közös adatok: email, név, stb.), de különböző "szerepkörök" vannak:

| User Típus         | Mit csinál?    | Speciális adatok                          |
| ------------------ | -------------- | ----------------------------------------- |
| **ItemWriter**     | Feladatokat ír | Milyen nyelveken/szinteken tud dolgozni   |
| **Translator**     | Fordít         | Milyen nyelvpárokkal dolgozik             |
| **Reviewer**       | Ellenőriz      | -                                         |
| **Examiner**       | Vizsgáztat     | Certification adatok (érvényesség, típus) |
| **InstituteAdmin** | Vizsgát rendel | Melyik institute-hoz tartozik             |

**Példa:**

- Alice (ItemWriter) → tud B2 szintű angol feladatot írni
- Bob (Translator) → tud angolról németre fordítani
- Carol (Examiner) → CEFR certification-je van → vizsgáztathat

**Probléma:** Jelenleg nincs tiszta TPH (Table-Per-Hierarchy) → EF Core nem tudja típus szerint lekérni őket.

---

## 1. 🔴 PROBLÉMA: Modulok túlzott mérete és felelőssége

> **ELI5:** Képzeld el, hogy egy szekrénybe összekeverve van minden: ruhák, könyvek, ételek, szerszámok. Így nehéz megtalálni, amit keresel, és ha bármit megváltoztatsz, félsz, hogy mást is elrontasz.

### Mi a probléma konkrétan?

**TestDevelopment Modul: 78 osztály egy helyen! 😱**

```
TestDevelopment/
├── TaskEntity, TaskRepository, EditTaskCommandHandler  (Task kezelés)
├── TaskGroupEntity, TaskGroupRepository  (TaskGroup kezelés)
├── CommentEntity, CommentRepository, AddCommentHandler  (Comment rendszer)
├── TestFileEntity, TestFileService, GetTestFileQueryHandler  (File kezelés)
├── TestVersionEntity, TestVersionRepository  (Verzió kezelés)
├── FieldEntity, ItemEntity, 14+ Validator  (Feladat struktúra)
└── ... még 50+ osztály
```

**Miért rossz ez?**

- ❌ Ha módosítasz egy Comment-et, félsz, hogy a Task kezelést elrontod
- ❌ Nehéz megtalálni a kódot ("hol van a file upload logika?")
- ❌ Új kolléga 2 hét alatt sem ismeri ki magát
- ❌ Unit test lassú (78 osztály függőségei)

**Ugyanez a Users modulnál is (30+ osztály):**

- User CRUD + Group management + Role kezelés + TablePreferences (UI state!) → mind egy helyen

**Javasolt refaktor:**

```
TestDevelopment/
├── Tasks/              (TaskEntity, TaskRepository, Task handlers)
├── TaskGroups/         (TaskGroupEntity, assignment logic)
├── Comments/           (CommentEntity, CommentRepository)
├── TestFiles/          (TestFileEntity, file operations)
├── TestVersions/       (TestVersionEntity, version management)
└── Structure/          (Field entities, validation)
```

### Users Modul (30+ osztály)

**Problémák:**

- User management, Groups, Roles, TablePreferences keverednek
- Nincs TPH (Table-Per-Hierarchy) vagy TPT user típusokra

**Javasolt szétbontás:**

```
Users/
├── Core/              (BaseUserEntity, CRUD)
├── Groups/            (Group management, KeyCloak sync)
├── Preferences/       (TablePreferenceEntity)
└── LanguageLevels/    (UserLanguageLevelEntity)
```

---

## 2. 🔴 PROBLÉMA: KeyCloak integráció szétszóródása

> **ELI5:** Képzeld el, hogy minden alkalommal, amikor be akarsz lépni a lakásodba, fel kell hívnod a portást telefonon. Még akkor is, ha 5 perce csináltad. És ha a telefon nem működik, nem tudsz bejutni.

### Mi a probléma?

**Jelenleg:** Minden művelethez (feladat szerkesztése, user lista lekérés, stb.) **HTTP hívás megy a KeyCloak API-ba**.

**Példa - Task szerkesztés:**

```csharp
// TaskService.EditTask() - 280. sor környékén
var userRoles = await keyCloakService.GetRolesForUserAsync(userId);  // ← HTTP hívás!
var userHasRight = userRoles.Select(x => x.Name).Contains(Scopes.TestDevelopment);

if (!isUserAssigned && !userHasRight)
    throw new BusinessException("Unauthorized");
```

**Következmények:**

- ⏱️ **Lassú:** 200-500ms minden request (+HTTP latency)
- 🔥 **Nem skálázódik:** Ha KeyCloak leáll/lassú → teljes rendszer áll
- 🧪 **Tesztelhetetlen:** Unit test-hez mock KeyCloak API kell
- 🔗 **Erős coupling:** Ha LDAP-ra/Auth0-ra váltasz → minden modult át kell írni

**User lista lekérés még rosszabb:**

```csharp
// GetUsersByStatusQuery - MINDEN role-hoz külön HTTP hívás!
foreach (var role in roles)  // pl. 5 role
{
    var userIds = await keyCloakService.GetAllUsersByRoleIdAsync(role, ct);  // 5 HTTP hívás!
    // ...
}
// Összesen: 500-1000ms! 😱
```

### KeyCloak Struktúra (ahogy TI használjátok)

**Fontos megérteni:** KeyCloak-nál nincs "role", hanem **client roles** = **permissions** (jogosultságok).

**JWT token példa (amit a backend kap):**

```json
{
  "sub": "user-keycloak-id-12345",
  "email": "alice@example.com",
  "resource_access": {
    "fide-client": {
      "roles": [
        "ItemWriter", // ← Ez NEM role, hanem permission!
        "TaskTranslation", // ← "Jogom van fordítani"
        "EditOwnTask", // ← "Jogom van saját task-ot szerkeszteni"
        "TestDevelopment" // ← "Admin jogom van (mindent szerkeszthetek)"
      ]
    }
  }
}
```

**Groups (user csoportok KeyCloak-ban):**

- **Admin** → minden permission (40+ darab)
- **TestDeveloper** → task development permissions (EditOwnTask, TaskCreation, TaskReview, stb.)
- **Translator** → translation permissions (TaskTranslation, EditOwnTask)
- **ItemWriter** → item writing permissions (ItemWriter, EditOwnTask, TaskCreation)
- **Institute** → order management permissions (OrderCreation, OrderObservation)

**Példa:** Alice (ItemWriter) = KeyCloak-ban benne van az "ItemWriter" Group-ban → automatikusan kap 10+ permission-t.

---

## 3. 🔴 PROBLÉMA: Authorization logika duplikáció + SECURITY HOLE!

> **ELI5:** A lakásod ajtaján van egy zár (KeyCloak permission check), DE bárki, akinek kulcsa van, kinyithatja BÁRMELYIK lakást az épületben. Nem ellenőrzi, hogy az a TE lakásod-e.

### Mi a konkrét probléma?

**Jelenlegi védelem (2 helyen, inkonzisztensen):**

#### 1. Controller (csak permission check)

```csharp
[Authorize(Policy = Scopes.EditOwnTask)]  // ← "Van-e EditOwnTask permission-je?"
[HttpPut]
public async Task<IActionResult> Update([FromForm] EditTaskCommand command, ...)
{
    await _mediator.Send(command, cancellationToken);
    return Ok();
}
```

→ Ez csak azt ellenőrzi, hogy a user-nek VAN-E jogosultsága, de NEM azt, hogy EZT a konkrét task-ot szerkesztheti!

#### 2. TaskService (manuális, duplikált kód)

```csharp
// TaskService.EditTask() - 30+ sor
var isUserAssigned = existingTask.CurrentAssignedUser?.KeyCloakId == userId || ...;
var userRoles = await keyCloakService.GetRolesForUserAsync(userId);  // HTTP!
var userHasRight = userRoles.Select(x => x.Name).Contains(Scopes.TestDevelopment);

if (!isUserAssigned && !userHasRight)
    throw new BusinessException("Unauthorized");
```

→ Ez ellenőrzi, DE lassú (HTTP hívás), duplikált, és nincs mindenhol implementálva!

### 🚨 SECURITY HOLE - Exploit példa

**Alice (ItemWriter) támadás:**

```http
PUT /api/task
Authorization: Bearer <Alice token, van EditOwnTask permission-je>
Content-Type: application/json

{
  "taskId": "bob-task-ja-guid",  // ← Bob task-ja, NEM Alice-é!
  "fields": "{...hacked content...}"
}
```

**Mi történik?**

1. ✅ Controller: `[Authorize(Policy = Scopes.EditOwnTask)]` → Alice-nak VAN EditOwnTask → **PASS**
2. ❌ Service: Ha a service-ben NINCS ownership check (vagy nincs jól implementálva) → **EXPLOIT SIKERES!**

Alice módosította Bob task-ját! 😱

### Miért történik ez?

**Permission ≠ Authorization!**

- **Permission:** "Van-e jogod task-ot szerkeszteni általában?" (KeyCloak mondja meg)
- **Authorization:** "Szerkesztheted-e EZT a KONKRÉT task-ot?" (Backend domain rule)

**Jelenlegi probléma:** Sok helyen csak a Permission van ellenőrizve!

---

## 4. 🟠 PROBLÉMA: User lista lekérés KeyCloak hívásokkal

> **ELI5:** Minden alkalommal, amikor meg akarod nézni, "kik a fordítók?", fel kell hívnod a központi adminisztrációt (KeyCloak), és megkérdezni tőlük. Pedig van egy telefonkönyved (backend DB), csak nem bízol benne.

### Mi történik jelenleg? (GetUsersByStatusQuery)

**Példa használati eset:** TestDeveloper fordításba akarja küldeni a task-ot → UI mutatja a "rendelkezésre álló translator-okat".

```csharp
public async Task<IEnumerable<UserForAssignmentDto>> Handle(
    GetUsersByStatusQuery request,
    CancellationToken ct)
{
    var allKeyCloakUserIds = new HashSet<string>();
    var roles = StatusScopessMapping.GetScopesForStatus[request.Status];  // pl. ["TaskTranslation"]

    // 1. LÉPÉS: KeyCloak API hívások (LASSÚ!)
    foreach (var role in roles)  // Ha 5 role van → 5 HTTP hívás!
    {
        var userIds = await keyCloakService.GetAllUsersByRoleIdAsync(role, ct);  // HTTP!
        foreach (var id in userIds)
            allKeyCloakUserIds.Add(id);
    }

    // 2. LÉPÉS: Backend DB query (user adatok)
    var users = await userRepository.Find(
        u => u.Include(x => x.UserLanguageLevels).ThenInclude(ul => ul.Language),
        u => allKeyCloakUserIds.Contains(u.KeyCloakId ?? ""),
        ct);

    // 3. LÉPÉS: Filtering, mapping...
    return users.Select(u => u.ToUserForAssignmentDto(...));
}
```

**Performance mérés:**

- KeyCloak hívások: 5 role × 100ms = **500ms** ⏱️
- DB query: **50ms** ⚡
- **Összesen: 550ms** (és ez MINDEN request-nél újra lefut!)

### Miért rossz ez?

❌ **Lassú:** 500-1000ms latency (user experience rossz)  
❌ **Nem skálázódik:** Ha 100 translator van → 100+ user data a KeyCloak-ból  
❌ **Felesleges:** A backend DB-ben MÁR MEGVAN, ki milyen user! Csak nincs cache-elve  
❌ **Race condition:** Ha user role-ja változik KeyCloak-ban, a backend nem tudja róla (sync issue)

---

## 5. 🟡 PROBLÉMA: Domain model hiányosságok

> **ELI5:** Képzeld el, hogy van egy "Család" fogalmad (Anya + Apa + Gyerekek), DE a kódban csak a gyerekek léteznek egyenként, és nincs egy "Család" objektum, ami összefogná őket. Így nehéz megválaszolni: "Ez a család készen áll a nyaralásra?" (minden gyerek bepakolt?)

### Probléma 1: TaskGroup nem explicit Aggregate Root

**Mi a TaskGroup?** Egy feladat összes nyelvi változata (angol + német + francia Task → 1 TaskGroup).

**Jelenlegi kód:**

```csharp
public class TaskEntity
{
    public Guid TaskGroupId { get; set; }  // ← Csak ID, nincs explicit kapcsolat
    public Language Language { get; set; }  // German
    public TaskStatus Status { get; set; }  // Draft, InTranslation, Published...
}

// Nincs TaskGroupEntity! Csak implicit GroupId-k alapján csoportosítás.
```

**Probléma:**

- ❌ Nincs egyértelmű "owner": Ki menedzseli a TaskGroup lifecycle-t?
- ❌ Nehéz válaszolni: "Minden fordítás kész? Publikálható a TaskGroup?"
- ❌ Repository-k bonyolultak (JOIN-ok a GroupId alapján)

**Mit kellene csinálni?**

```csharp
public class TaskGroup  // Ez legyen az Aggregate Root!
{
    public Guid Id { get; set; }
    public Guid ScenarioId { get; set; }
    public TaskGroupStatus Status { get; set; }  // Draft, InProgress, Published

    private List<Task> _tasks = new();
    public IReadOnlyCollection<Task> Tasks => _tasks.AsReadOnly();

    // Domain logika ITT van!
    public bool CanPublish() => _tasks.All(t => t.Status == TaskStatus.Published);

    public void AddTranslation(Language language, UserId translator)
    {
        if (_tasks.Any(t => t.Language == language))
            throw new DuplicateTranslationException();

        var newTask = Task.CreateTranslation(Id, language, translator);
        _tasks.Add(newTask);
    }
}
```

### Probléma 2: User típusok nincs modellezve (TPH hiányzik)

**Mi a TPH?** Table-Per-Hierarchy = Egy táblában van minden user, de van egy "discriminator" oszlop, ami megmondja, milyen típusú.

**Jelenlegi helyzet:**

```csharp
public class BaseUserEntity { ... }
public class ExaminerEntity : BaseUserEntity { ... }
public class InstituteAdminEntity : BaseUserEntity { ... }
```

DE nincs TPH konfiguráció → EF Core külön táblákba teszi őket, és nehéz lekérdezni:

```csharp
// Ez NEM működik:
var examiner = await _userRepo.GetByIdAsync<ExaminerEntity>(userId);  // ❌
```

**Mit kellene?**

```csharp
// EF Core konfig (OnModelCreating)
modelBuilder.Entity<BaseUserEntity>()
    .HasDiscriminator<UserType>("UserType")
    .HasValue<ItemWriterEntity>(UserType.ItemWriter)
    .HasValue<ExaminerEntity>(UserType.Examiner);

// Most már működik:
var examiner = await _context.Users
    .OfType<ExaminerEntity>()  // ✅ Típus szerinti szűrés
    .Include(e => e.Certifications)
    .FirstOrDefaultAsync(e => e.Id == userId);
```

---

## 💡 MEGOLDÁSOK - Lépésről lépésre

> **Fontos:** Ne próbáld meg egyszerre az ÖSSZES problémát megoldani! Válassz EGY prioritást, implementáld, teszteld, utána menj tovább.

---

## MEGOLDÁS 1: Authorization Service bevezetése (Fázis 1 - 1 hét)

> **Cél:** Központi hely az authorization logikának + resource-based ellenőrzés + SECURITY HOLE bezárása

### Hogyan működik? (3 rétegű védelem)

```
┌─────────────────────────────────────────────────────────────┐
│                    AUTHORIZATION FLOW                        │
└─────────────────────────────────────────────────────────────┘

1. JWT Token érkezik → Controller
   ├─ KeyCloak validálja a JWT-t
   └─ Permissions (client roles) a token-ben vannak

2. [Authorize] Attribute a Controller-en
   ├─ "Van-e EditOwnTask permission-je?" (COARSE-GRAINED)
   └─ Ha nincs → 403 Forbidden (gyors elutasítás)

3. Command Handler / Service
   ├─ "EZT a konkrét task-ot szerkesztheti?" (FINE-GRAINED)
   ├─ "Ebben a státuszban szerkeszthető?" (DOMAIN RULE)
   └─ Ha nem → BusinessException (Unauthorized)
```

#### Layer 1: Controller (Coarse-grained permission check)

**Mit csinál?** Gyors elutasítás, ha a user-nek alapból nincs jogosultsága.

```csharp
// TaskController.cs
[Authorize(Policy = Scopes.EditOwnTask)]  // ← KeyCloak policy: "Van-e EditOwnTask permission?"
[HttpPut]
public async Task<IActionResult> Update([FromForm] EditTaskCommand command, CancellationToken ct)
{
    // Ha ide eljut a request → User-nek VAN EditOwnTask permission-je (JWT-ben van)
    await _mediator.Send(command, ct);
    return Ok();
}
```

**KeyCloak Policy konfig (Program.cs):**

```csharp
builder.Services.AddAuthorizationBuilder()
    .AddPolicy(Scopes.EditOwnTask, policy =>
        policy.Requirements.Add(new ResourceAccessRequirement(clientId!, [Scopes.EditOwnTask])));
```

**Mit ellenőriz?** JWT token → `resource_access.fide-client.roles` tartalmazza-e az `"EditOwnTask"` stringet?

**Elég ez?** ❌ **NEM!** Mert egy ItemWriter más ItemWriter task-ját is szerkeszthetné (ha van permission-je).

#### Layer 2: Command Handler (Fine-grained resource check)

```csharp
public class EditTaskCommandHandler : IRequestHandler<EditTaskCommand, Result>
{
    private readonly ITaskAuthorizationService _authz;

    public async Task<Result> Handle(EditTaskCommand request, CancellationToken ct)
    {
        var task = await _taskRepo.GetByIdAsync(request.TaskId, ct);
        var userId = _httpContext.HttpContext.User.FindFirst("sub")?.Value;

        // Resource-based authorization
        var authResult = await _authz.CanEditTaskAsync(task, userId);
        if (!authResult.IsAuthorized)
            return Result.Fail(authResult.Reason);

        // Business logic
        await _taskService.EditTask(task, request.Fields, ct);
        return Result.Ok();
    }
}
```

#### Layer 3: Authorization Service (Domain rules + Role overrides)

```csharp
public class TaskAuthorizationService : ITaskAuthorizationService
{
    private readonly IIdentityProvider _identityProvider;  // KeyCloak wrapper

    public async Task<AuthorizationResult> CanEditTaskAsync(TaskEntity task, string userId)
    {
        // 1. Admin override
        var userRoles = await _identityProvider.GetUserRolesAsync(userId);
        if (userRoles.Contains("TestDevelopment"))
            return AuthorizationResult.Success("Admin override");

        // 2. Status check (domain rule)
        if (!IsTaskEditable(task.Status))
            return AuthorizationResult.Fail($"Task in non-editable status: {task.Status}");

        // 3. Ownership check (resource-based)
        if (!IsUserAssignedToTask(task, userId))
            return AuthorizationResult.Fail("User not assigned to this task");

        return AuthorizationResult.Success();
    }

    private bool IsTaskEditable(TaskStatus status) =>
        status == TaskStatus.Draft ||
        status == TaskStatus.InTranslation ||
        status == TaskStatus.InTranslationAfterReview;

    private bool IsUserAssignedToTask(TaskEntity task, string userId) =>
        task.CurrentAssignedUser?.KeyCloakId == userId ||
        task.ItemWriter?.KeyCloakId == userId ||
        task.Translator?.KeyCloakId == userId;
}
```

**TaskService CLEAN lesz:**

```csharp
// TÖRÖLD a 30+ sor KeyCloak authorization kódot!
public async Task<bool> EditTask(TaskEntity existingTask, string fields, ...)
{
    // Csak üzleti logika
    var fieldHandlers = InitializeFieldHandlers();
    // ...
}
```

---

## MEGOLDÁS 2: User Role Cache (Backend DB-ben) - Fázis 2 (2 hét)

> **Cél:** Megszabadulni a KeyCloak HTTP hívások 90%-ától → 10x gyorsabb user lista lekérés

### Hogyan működik?

```
┌────────────────────────────────────────────────────────────┐
│                   ROLE CACHE STRATÉGIA                      │
└────────────────────────────────────────────────────────────┘

1. User Login
   ├─ JWT validálás (KeyCloak)
   └─ Middleware: Background sync role-ok → Backend DB

2. Role-ok tárolása Backend DB-ben (cache)
   ├─ UserRoleEntity tábla: user_id, role_name, cached_at
   └─ Frissítés: Login (instant) + Background job (6 óránként)

3. Query (pl. "Kik a translatorok?")
   ├─ Backend DB query (NINCS KeyCloak hívás!)
   └─ 20-50ms (volt: 500-1000ms) ⚡

4. Role változás (KeyCloak-ban)
   ├─ Webhook (real-time) VAGY
   └─ Next login + Background job (eventual consistency)
```

### Lépés 1: User Entity kiegészítése (cache structure)

```csharp
// Entities/Users/BaseUserEntity.cs
public class BaseUserEntity
{
    public Guid Id { get; set; }
    public string Email { get; set; }
    public string? KeyCloakId { get; set; }

    // ÚJ: Role cache (backend-en tároljuk)
    public List<UserRoleEntity> CachedRoles { get; set; } = new();
    public DateTime? RolesCachedAt { get; set; }  // Mikor cache-eltük utoljára?

    // Existing
    public List<UserLanguageLevelEntity> UserLanguageLevels { get; set; }
}

// ÚJ entitás: UserRoleEntity
public class UserRoleEntity
{
    public Guid Id { get; set; }
    public Guid UserId { get; set; }
    public BaseUserEntity User { get; set; }

    public string RoleName { get; set; }  // "TaskTranslation", "ItemWriter", "TestDevelopment"
    public DateTime AssignedAt { get; set; }
}
```

**EF Core konfiguráció (OnModelCreating):**

```csharp
// FideDbContext.cs
protected override void OnModelCreating(ModelBuilder modelBuilder)
{
    modelBuilder.Entity<BaseUserEntity>()
        .HasMany(u => u.CachedRoles)
        .WithOne(r => r.User)
        .HasForeignKey(r => r.UserId)
        .OnDelete(DeleteBehavior.Cascade);  // Ha user törlődik → role-ok is

    modelBuilder.Entity<UserRoleEntity>()
        .HasIndex(r => r.RoleName);  // Index a gyors query-hez (WHERE RoleName = ...)

    modelBuilder.Entity<UserRoleEntity>()
        .HasIndex(r => new { r.UserId, r.RoleName })
        .IsUnique();  // Egy user-nek ugyanaz a role csak 1x lehet
}
```

**Migration létrehozása:**

```bash
dotnet ef migrations add AddUserRoleCache
dotnet ef database update
```

### Lépés 2: Sync Service (KeyCloak → Backend)

```csharp
// Application/Services/UserRoleSyncService.cs
public class UserRoleSyncService : IUserRoleSyncService
{
    private readonly IKeyCloakService _keyCloakService;
    private readonly IUserRepository _userRepo;
    private readonly IMemoryCache _cache;
    private readonly TimeSpan _cacheExpiration = TimeSpan.FromHours(1);

    // Sync egy user role-jait (login-kor hívódik)
    public async Task SyncUserRolesAsync(string keyCloakId, CancellationToken ct = default)
    {
        var user = await _userRepo.GetByKeyCloakIdAsync(keyCloakId, ct);
        if (user == null) return;

        // Ellenőrizzük, hogy friss-e a cache (1 óránál nem régebbi)
        if (user.RolesCachedAt.HasValue &&
            DateTime.UtcNow - user.RolesCachedAt.Value < _cacheExpiration)
        {
            return; // Nem kell frissíteni, friss a cache
        }

        // KeyCloak-ból lekérjük a role-okat (HTTP hívás, DE ritkán!)
        var kcRoles = await _keyCloakService.GetRolesForUserAsync(keyCloakId, ct);
        var roleNames = kcRoles.Select(r => r.Name).ToList();

        // Backend DB update (átírjuk a cache-t)
        user.CachedRoles.Clear();
        foreach (var roleName in roleNames)
        {
            user.CachedRoles.Add(new UserRoleEntity
            {
                Id = Guid.NewGuid(),
                UserId = user.Id,
                RoleName = roleName,
                AssignedAt = DateTime.UtcNow
            });
        }

        user.RolesCachedAt = DateTime.UtcNow;
        await _userRepo.UpdateAsync(user, ct);

        // Memory cache is frissítjük (gyorsabb lekérés, ha kell)
        _cache.Set($"user_roles_{keyCloakId}", roleNames, _cacheExpiration);
    }

    // Bulk sync (minden user role-jait frissíti - background job-ból hívva)
    public async Task SyncAllUserRolesAsync(CancellationToken ct = default)
    {
        var users = await _userRepo.GetAllAsync(ct);

        foreach (var user in users)
        {
            if (string.IsNullOrEmpty(user.KeyCloakId)) continue;

            try
            {
                await SyncUserRolesAsync(user.KeyCloakId, ct);
            }
            catch (Exception ex)
            {
                // Log error, de folytatjuk a többi user-rel (resilience)
                Console.WriteLine($"Failed to sync user {user.Email}: {ex.Message}");
            }
        }
    }
}
```

**Regisztráció (Program.cs):**

```csharp
builder.Services.AddScoped<IUserRoleSyncService, UserRoleSyncService>();
```

### Lépés 3: Middleware (Login-kor automatikus sync)

```csharp
// Middleware/UserRoleSyncMiddleware.cs
public class UserRoleSyncMiddleware
{
    private readonly RequestDelegate _next;

    public async Task InvokeAsync(
        HttpContext context,
        IUserRoleSyncService syncService)
    {
        if (context.User.Identity?.IsAuthenticated == true)
        {
            var keyCloakId = context.User.FindFirst("sub")?.Value;

            if (!string.IsNullOrEmpty(keyCloakId))
            {
                // Background sync (NEM blockol! User nem vár rá)
                _ = Task.Run(async () =>
                {
                    try
                    {
                        await syncService.SyncUserRolesAsync(keyCloakId);
                    }
                    catch
                    {
                        // Silent fail (ne dobjon exception login-kor)
                        // De production-ben log-old!
                    }
                });
            }
        }

        await _next(context);
    }
}
```

**Regisztráció (Program.cs):**

```csharp
app.UseAuthentication();
app.UseMiddleware<UserRoleSyncMiddleware>();  // ← Login után, Authorization előtt
app.UseAuthorization();
```

**Mit csinál?**

- User bejelentkezik → JWT token validálás (KeyCloak)
- Middleware: "Hmm, ez a user be van jelentkezve, sync-eljük a role-jait (background-ban)"
- User rögtön használhatja az appot, közben a háttérben frissül a cache

### Lépés 4: Refaktorált Query (10x gyorsabb!)

**ELŐTTE (GetUsersByStatusQuery - LASSÚ):**

```csharp
public async Task<IEnumerable<UserForAssignmentDto>> Handle(...)
{
    // ❌ KeyCloak API hívások (5-10 HTTP request!)
    foreach (var role in roles)
    {
        var userIds = await keyCloakService.GetAllUsersByRoleIdAsync(role, ct);  // HTTP!
        // ...
    }
    // 500-1000ms ⏱️
}
```

**UTÁNA (Backend DB query - GYORS!):**

```csharp
public async Task<IEnumerable<UserForAssignmentDto>> Handle(
    GetUsersByStatusQuery request,
    CancellationToken ct)
{
    // 1. Meghatározzuk, milyen role-ok kellenek
    var requiredRoles = StatusScopessMapping.GetScopesForStatus[request.Status];

    // 2. Task lekérése (ki van már assignolva?)
    var task = await _taskRepo.FindOneAsync(t => t.Id == request.TaskId, ct);

    // 3. ✅ User-ek lekérése BACKEND DB-ből (NINCS KeyCloak hívás!)
    var users = await _userRepo.Find(
        query => query
            .Include(u => u.CachedRoles)  // ← Cached roles JOIN
            .Include(u => u.UserLanguageLevels)
                .ThenInclude(ul => ul.Language),
        u => u.CachedRoles.Any(r => requiredRoles.Contains(r.RoleName)),  // ← DB-ben szűrünk!
        ct
    );

    // 4. Language filtering (ha Reviewer/Translator → csak megfelelő nyelvű user-ek)
    if (StatusToActionMapping.ReviewerStatuses.Contains(request.Status))
    {
        users = users.Where(u =>
            u.UserLanguageLevels.Any(ul => ul.Language.Language == request.Language)
        ).ToList();
    }

    // 5. DTO mapping
    return users.Select(u => u.ToUserForAssignmentDto(
        isSelected: task?.GetAssignedUserId() == u.Id
    ));

    // ✅ 20-50ms (volt: 500-1000ms) ⚡
}
```

**Performance összehasonlítás:**
| Metrika | Előtte | Utána | Javulás |
|---------|--------|-------|---------|
| **Query idő** | 500-1000ms | 20-50ms | **20x gyorsabb** |
| **HTTP request-ek** | 5-10 | 0 | **Nincs network hívás** |
| **DB query-k** | 1 (user filter) | 1 (user + role JOIN) | Változatlan |
| **Cache hit rate** | 0% | ~90% | **Drastikusan jobb** |

---

## MEGOLDÁS 3: 🔴 Real-time Notifications (SignalR) - BONUS Feature!

> **Cél:** Ha valaki módosít egy task-ot, AZONNAL látják a többiek (collaborative editing, mint Google Docs)

### Miért kell SignalR?

**Jelenlegi probléma:**

- Alice szerkeszti a Task-ot → Mentés
- Bob ugyanazt a Task-ot nézi → **NEM látja Alice változtatását**, amíg nem frissíti az oldalt (F5)
- Race condition: Bob is szerkeszt → Felülírja Alice változtatását!

**SignalR megoldás:**

- Alice mentés → Backend → **SignalR broadcast** → Bob browser-ében **automatikusan frissül**
- Real-time notifications: "Alice épp szerkeszti ezt a Task-ot" (presence indicator)

### Implementáció (egyszerűen)

#### 1. SignalR Hub létrehozása

```csharp
// Hubs/TaskHub.cs
public class TaskHub : Hub
{
    // User csatlakozik egy Task "room"-hoz (amikor megnyitja a Task-ot)
    public async Task JoinTaskRoom(Guid taskId)
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, $"task_{taskId}");

        // Értesítjük a többieket: "Alice csatlakozott"
        await Clients.OthersInGroup($"task_{taskId}")
            .SendAsync("UserJoined", new
            {
                UserId = Context.UserIdentifier,
                UserName = Context.User?.Identity?.Name,
                TaskId = taskId
            });
    }

    // User elhagyja a Task-ot (bezárja a lapot)
    public async Task LeaveTaskRoom(Guid taskId)
    {
        await Groups.RemoveFromGroupAsync(Context.ConnectionId, $"task_{taskId}");

        await Clients.OthersInGroup($"task_{taskId}")
            .SendAsync("UserLeft", new
            {
                UserId = Context.UserIdentifier,
                TaskId = taskId
            });
    }

    // User elkezd gépelni (typing indicator)
    public async Task NotifyTyping(Guid taskId, string fieldName)
    {
        await Clients.OthersInGroup($"task_{taskId}")
            .SendAsync("UserTyping", new
            {
                UserId = Context.UserIdentifier,
                UserName = Context.User?.Identity?.Name,
                TaskId = taskId,
                FieldName = fieldName
            });
    }
}
```

#### 2. Domain Event → SignalR Notification

```csharp
// Application/EventHandlers/TaskUpdatedEventHandler.cs
public class TaskUpdatedEventHandler : INotificationHandler<TaskUpdatedEvent>
{
    private readonly IHubContext<TaskHub> _hubContext;

    public async Task Handle(TaskUpdatedEvent evt, CancellationToken ct)
    {
        // Broadcast minden user-nek, aki épp nézi ezt a Task-ot
        await _hubContext.Clients
            .Group($"task_{evt.TaskId}")
            .SendAsync("TaskUpdated", new
            {
                TaskId = evt.TaskId,
                UpdatedBy = evt.UserId,
                UpdatedFields = evt.ChangedFields,
                Timestamp = DateTime.UtcNow
            }, ct);
    }
}
```

#### 3. EditTaskCommandHandler integráció

```csharp
public class EditTaskCommandHandler : IRequestHandler<EditTaskCommand, Result>
{
    private readonly IMediator _mediator;

    public async Task<Result> Handle(EditTaskCommand request, CancellationToken ct)
    {
        // Authorization + Business logic...
        await _taskService.EditTask(task, request.Fields, ct);

        // ✅ Domain Event → SignalR notification
        await _mediator.Publish(new TaskUpdatedEvent
        {
            TaskId = task.Id,
            UserId = userId,
            ChangedFields = GetChangedFields(task)  // Diff calculation
        }, ct);

        return Result.Ok();
    }
}
```

#### 4. Frontend (React/Angular példa)

```typescript
// Frontend: SignalR connection
import * as signalR from "@microsoft/signalr";

const connection = new signalR.HubConnectionBuilder()
  .withUrl("/hubs/task")
  .withAutomaticReconnect()
  .build();

// Subscribe to events
connection.on("TaskUpdated", (data) => {
  console.log(`Task ${data.taskId} was updated by ${data.updatedBy}`);

  // UI frissítés (React state update)
  setTaskData((prevData) => ({
    ...prevData,
    ...data.updatedFields,
  }));

  // Toast notification
  toast.info(`${data.updatedBy} módosította a feladatot`);
});

connection.on("UserJoined", (data) => {
  // Presence indicator: "Alice is viewing this task"
  setActiveUsers((prev) => [...prev, data]);
});

connection.on("UserTyping", (data) => {
  // Typing indicator: "Bob is typing in Field 3..."
  showTypingIndicator(data.userName, data.fieldName);
});

// Join task room when opening a task
await connection.invoke("JoinTaskRoom", taskId);
```

#### 5. Program.cs konfiguráció

```csharp
// Add SignalR
builder.Services.AddSignalR();

// Map Hub endpoint
app.MapHub<TaskHub>("/hubs/task");
```

### SignalR Use Cases a FIDE-ban

| Use Case                      | SignalR Event         | UX Benefit                                  |
| ----------------------------- | --------------------- | ------------------------------------------- |
| **Task szerkesztés**          | `TaskUpdated`         | Real-time sync (mint Google Docs)           |
| **Task status változás**      | `TaskStatusChanged`   | UI azonnal frissül (Draft → InReview)       |
| **Assignment változás**       | `TaskAssigned`        | "Ez a feladat rád van osztva!" notification |
| **Comment hozzáadás**         | `CommentAdded`        | Új comment azonnal látszik                  |
| **Translation task creation** | `TranslationCreated`  | Translator azonnal értesül                  |
| **Presence**                  | `UserJoined/UserLeft` | "Alice is viewing this task"                |
| **Typing indicator**          | `UserTyping`          | "Bob is editing Field 3..."                 |

### Előnyök

✅ **Collaborative editing** (többen dolgozhatnak egy feladaton)  
✅ **Konfliktuselkerülés** (látják, ki szerkeszt)  
✅ **Jobb UX** (nincs szükség F5-re)  
✅ **Real-time notifications** (pl. "Új feladatot kaptál!")

---

## MEGOLDÁS 4: Module Refactoring (Fázis 3 - 3 hét)

> **Cél:** 78 osztályos monolith → 6 kisebb, átlátható modul

### Javasolt struktúra

```
TestDevelopment/
├── Tasks/
│   ├── Entities/TaskEntity.cs
│   ├── Repository/TaskRepository.cs
│   ├── Commands/EditTaskCommand.cs, DeleteTaskCommand.cs
│   ├── Queries/GetTaskByIdQuery.cs
│   └── Handlers/EditTaskCommandHandler.cs, GetTaskByIdQueryHandler.cs
│
├── TaskGroups/
│   ├── Entities/TaskGroupEntity.cs  (ÚJ Aggregate Root!)
│   ├── Repository/TaskGroupRepository.cs
│   ├── Commands/CreateTaskGroupCommand.cs, PublishTaskGroupCommand.cs
│   └── Handlers/...
│
├── Comments/
│   ├── Entities/CommentEntity.cs
│   ├── Repository/CommentRepository.cs
│   ├── Commands/AddCommentCommand.cs
│   └── Handlers/...
│
├── TestFiles/
│   ├── Entities/TestFileEntity.cs
│   ├── Services/TestFileService.cs
│   ├── Repository/TestFileRepository.cs
│   └── Commands/UploadTestFileCommand.cs
│
├── TestVersions/
│   ├── Entities/TestVersionEntity.cs
│   ├── Repository/TestVersionRepository.cs
│   └── Commands/CreateTestVersionCommand.cs
│
└── Structure/  (Field/Item validáció)
    ├── Entities/FieldEntity.cs, ItemEntity.cs
    ├── Validators/AudioFileValidator.cs, ItemsValidator.cs, ...
    └── Services/FieldValidationService.cs
```

### Refaktor lépések (példa: Tasks modul kiemelése)

**1. Új mappa létrehozása:**

```bash
mkdir -p Application/TestDevelopment/Tasks/{Entities,Repository,Commands,Queries,Handlers}
```

**2. Osztályok áthelyezése:**

```bash
# Entities
mv TaskEntity.cs → Application/TestDevelopment/Tasks/Entities/
mv TaskEntityExtensions.cs → Application/TestDevelopment/Tasks/Entities/

# Repository
mv TaskRepository.cs → Application/TestDevelopment/Tasks/Repository/
mv ITaskRepository.cs → Application/TestDevelopment/Tasks/Repository/

# Commands
mv EditTaskCommand.cs → Application/TestDevelopment/Tasks/Commands/
mv DeleteTaskCommand.cs → Application/TestDevelopment/Tasks/Commands/

# Handlers
mv EditTaskCommandHandler.cs → Application/TestDevelopment/Tasks/Handlers/
```

**3. Namespace frissítése:**

```csharp
// Előtte
namespace Fide.Application.Entities.TestDevelopment;

// Utána
namespace Fide.Application.TestDevelopment.Tasks.Entities;
```

**4. Using-ok javítása (IDE auto-fix):**

```csharp
using Fide.Application.TestDevelopment.Tasks.Entities;
using Fide.Application.TestDevelopment.Tasks.Repository;
```

**5. Circular dependency elkerülése:**

```csharp
// ❌ ROSSZ: Tasks → TaskGroups → Tasks (circular!)

// ✅ JÓ: Shared modul közös interface-ekhez
TestDevelopment/
├── Shared/
│   └── ITaskGroupRepository.cs  (interface)
├── Tasks/
│   └── használja ITaskGroupRepository-t
└── TaskGroups/
    └── implementálja ITaskGroupRepository-t
```

---

## MEGOLDÁS 5: Domain Model tisztítása (Fázis 4 - 2 hét)

### TaskGroup Aggregate Root implementáció

```csharp
// Domain/TaskGroup.cs
public class TaskGroup  // Aggregate Root
{
    public Guid Id { get; private set; }
    public Guid ScenarioId { get; private set; }
    public TaskGroupStatus Status { get; private set; }
    public DateTime CreatedAt { get; private set; }
    public DateTime UpdatedAt { get; private set; }

    private readonly List<Task> _tasks = new();
    public IReadOnlyCollection<Task> Tasks => _tasks.AsReadOnly();

    private readonly List<IDomainEvent> _domainEvents = new();
    public IReadOnlyCollection<IDomainEvent> DomainEvents => _domainEvents.AsReadOnly();

    // Factory method (domain logic)
    public static TaskGroup Create(Guid scenarioId, Guid createdBy, List<Language> initialLanguages)
    {
        var taskGroup = new TaskGroup
        {
            Id = Guid.NewGuid(),
            ScenarioId = scenarioId,
            Status = TaskGroupStatus.Draft,
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow
        };

        // Automatically create initial language tasks
        foreach (var language in initialLanguages)
        {
            taskGroup.AddTranslation(language, createdBy);
        }

        taskGroup._domainEvents.Add(new TaskGroupCreatedEvent(taskGroup.Id, scenarioId));
        return taskGroup;
    }

    // Domain operation: Add translation
    public void AddTranslation(Language language, Guid translatorId)
    {
        if (_tasks.Any(t => t.Language == language))
            throw new DomainException($"Translation for {language} already exists");

        var newTask = Task.CreateTranslation(Id, language, translatorId);
        _tasks.Add(newTask);

        _domainEvents.Add(new TranslationTaskCreatedEvent(Id, language, translatorId));
    }

    // Domain query: Can publish?
    public bool CanPublish()
    {
        return _tasks.All(t => t.Status == TaskStatus.Published) &&
               _tasks.Count > 0;
    }

    // Domain operation: Publish
    public void Publish()
    {
        if (!CanPublish())
            throw new DomainException("Not all translations are ready for publishing");

        Status = TaskGroupStatus.Published;
        UpdatedAt = DateTime.UtcNow;

        _domainEvents.Add(new TaskGroupPublishedEvent(Id));
    }

    public void ClearDomainEvents() => _domainEvents.Clear();
}

// Domain Events
public record TaskGroupCreatedEvent(Guid TaskGroupId, Guid ScenarioId) : IDomainEvent;
public record TranslationTaskCreatedEvent(Guid TaskGroupId, Language Language, Guid TranslatorId) : IDomainEvent;
public record TaskGroupPublishedEvent(Guid TaskGroupId) : IDomainEvent;
```

### Repository pattern (Aggregate Root-friendly)

```csharp
// Repository loads the ENTIRE Aggregate
public class TaskGroupRepository : ITaskGroupRepository
{
    public async Task<TaskGroup> GetWithAllDataAsync(Guid id, CancellationToken ct)
    {
        return await _context.TaskGroups
            .Include(tg => tg.Tasks)
                .ThenInclude(t => t.Fields)
                    .ThenInclude(f => f.Items)
            .FirstOrDefaultAsync(tg => tg.Id == id, ct);
    }

    public async Task SaveAsync(TaskGroup taskGroup, CancellationToken ct)
    {
        // Save aggregate
        _context.TaskGroups.Update(taskGroup);

        // Dispatch domain events (SignalR notifications!)
        foreach (var domainEvent in taskGroup.DomainEvents)
        {
            await _mediator.Publish(domainEvent, ct);
        }

        taskGroup.ClearDomainEvents();
        await _context.SaveChangesAsync(ct);
    }
}
```

---

## 📊 REFAKTOR PRIORITÁSOK (Reális Ütemterv)

### ✅ Fázis 1: Quick Wins (1 hét) - KRITIKUS!

**Cél:** Security hole bezárása + Leggyakoribb műveletek gyorsítása

**Lépések:**

1. **TaskAuthorizationService létrehozása** (2 nap)
   - Interface + implementáció
   - `CanEditTaskAsync()`, `CanTranslateTaskAsync()`, `CanReviewTaskAsync()`
2. **EditTaskCommandHandler refaktor** (1 nap)
   - KeyCloak hívás → `_authz.CanEditTaskAsync()`
   - Unit tesztek írása
3. **TaskService cleanup** (1 nap)

   - 30+ sor authorization kód törlése
   - `KeyCloakService` dependency eltávolítása
   - Meglévő tesztek javítása

4. **Hiányzó [Authorize] attribute-ok** (1 nap)
   - Controller audit (minden endpoint ellenőrzése)
   - Security testing

**Várható eredmény:**

- ✅ Security hole bezárva
- ✅ EditTask 50-100ms gyorsabb
- ✅ Tesztelhető kód

---

### ✅ Fázis 2: User Role Cache (2 hét)

**Cél:** 90% kevesebb KeyCloak hívás → 10x gyorsabb user query-k

**Lépések:**

1. **Database setup** (2 nap)

   - `UserRoleEntity` létrehozása
   - EF Core migration
   - Indexek létrehozása

2. **UserRoleSyncService implementáció** (2 nap)

   - `SyncUserRolesAsync()` metódus
   - Cache expiration logika (1 óra)
   - Error handling

3. **Middleware + sync** (2 nap)

   - `UserRoleSyncMiddleware` (login-kor sync)
   - Migration script (meglévő user-ek sync-je)
   - Testing

4. **Query refaktor** (2 nap)

   - `GetUsersByStatusQueryHandler` átírása
   - `UserRepository` extension metódusok
   - Performance testing (benchmark)

5. **Background job** (2 nap)
   - `UserRoleSyncJob` (6 óránként sync)
   - Monitoring/logging
   - Alert ha sync fail

**Várható eredmény:**

- ✅ User query: 20-50ms (volt: 500-1000ms)
- ✅ 90% cache hit rate
- ✅ Skálázhatóság javul

---

### ✅ Fázis 3: Module Refactoring (3 hét)

**Cél:** Átláthatóbb kódstruktúra → könnyebb karbantartás

**Lépések:**

1. **Tasks modul kiemelése** (1 hét)

   - Mappa struktúra létrehozása
   - Osztályok áthelyezése
   - Namespace + using frissítése
   - Tesztek futtatása

2. **TaskGroups modul** (3 nap)

   - TaskGroup Aggregate Root
   - Repository implementation
   - Domain events

3. **Comments + TestFiles modul** (4 nap)
   - Modulok szétválasztása
   - Interface-ek tisztázása

**Várható eredmény:**

- ✅ 6 kisebb modul (15-20 osztály/modul)
- ✅ Új feature 2x gyorsabban implementálható
- ✅ Onboarding 50% gyorsabb

---

### ✅ Fázis 4: Domain Model + SignalR (2 hét)

**Cél:** Üzleti logika explicit modellezése + Real-time UX

**Lépések:**

1. **TaskGroup Aggregate Root** (3 nap)

   - Domain logic implementálása
   - Factory methods
   - Domain events

2. **TPH bevezetése User típusokra** (2 nap)

   - EF Core konfiguráció
   - Migration
   - Repository query-k frissítése

3. **SignalR integráció** (3 nap)

   - `TaskHub` létrehozása
   - Domain Event → SignalR handler
   - Frontend integration példák

4. **Testing + dokumentáció** (2 nap)
   - Integration tesztek
   - API dokumentáció frissítése

**Várható eredmény:**

- ✅ Üzleti szabályok explicit (1 helyen)
- ✅ Real-time notifications (UX++)
- ✅ Collaborative editing (mint Google Docs)

---

## 🚨 KRITIKUS SECURITY JAVÍTÁSOK (AZONNAL!)

### 1. Hiányzó [Authorize] attribute-ok (Controller audit)

**Ellenőrzendő endpoint-ok:**

```csharp
// TaskController.cs
[HttpGet("Group/{taskGroupId}/translatable-languages")]  // ← NINCS [Authorize]!
[HttpPut("User")]  // ← NINCS [Authorize]!

// Javítás:
[Authorize(Policy = Scopes.TaskObservation)]
[HttpGet("Group/{taskGroupId}/translatable-languages")]

[Authorize(Policy = Scopes.TaskAssignment)]  // ← Új policy kell!
[HttpPut("User")]
```

**Action item:** Végigmenni MINDEN Controller-en, ellenőrizni, hogy minden public endpoint védett-e.

### 2. Resource-based authorization hiánya

**Jelenlegi exploit:**

```http
PUT /api/task
Authorization: Bearer <ItemWriter token>
{
  "taskId": "mas-user-task-ja",
  "fields": "hacked"
}
```

→ ✅ Permission check PASS (van EditOwnTask)  
→ ❌ Resource check HIÁNYZIK → **EXPLOIT!**

**Javítás:** TaskAuthorizationService minden Command Handler-ben (Fázis 1).

---

## 📈 MÉRŐSZÁMOK (Cél vs Jelenlegi)

### Performance Metrics

| Metrika                      | Jelenlegi  | Cél (Refaktor után) | Javulás          |
| ---------------------------- | ---------- | ------------------- | ---------------- |
| **EditTask latency**         | 300-500ms  | 50-100ms            | **5x gyorsabb**  |
| **GetUsersByStatus**         | 500-1000ms | 20-50ms             | **20x gyorsabb** |
| **KeyCloak hívások/request** | 5-10       | 0-1                 | **10x kevesebb** |
| **Authorization check**      | 200-300ms  | 10-20ms             | **15x gyorsabb** |

### Code Quality Metrics

| Metrika                       | Jelenlegi      | Cél               |
| ----------------------------- | -------------- | ----------------- |
| **TestDevelopment osztályok** | 78             | 15-20 (6 almodul) |
| **Authorization duplikáció**  | 15+ hely       | 1 hely (Service)  |
| **Unit test coverage**        | ~40%           | 70%+              |
| **Coupling (modulok között)** | 10+ dependency | Max 5-6           |

### Business Metrics

| Metrika                      | Hatás                    |
| ---------------------------- | ------------------------ |
| **Security incidents**       | ↓ 100% (exploit bezárva) |
| **User satisfaction (UX)**   | ↑ 30% (gyorsabb app)     |
| **Developer velocity**       | ↑ 50% (tisztább kód)     |
| **Onboarding time (új dev)** | ↓ 50% (kisebb modulok)   |

---

## 🎯 ÖSSZEFOGLALÁS

### Legnagyobb problémák (prioritás szerint):

1. 🔴 **KRITIKUS - Security hole:** Bárki szerkesztheti más feladatát → **Fázis 1 (1 hét)**
2. 🔴 **KRITIKUS - Performance:** Lassú (500ms+) KeyCloak hívások → **Fázis 2 (2 hét)**
3. 🟠 **NAGY - Karbantarthatóság:** 78 osztályos monolith → **Fázis 3 (3 hét)**
4. 🟡 **KÖZEPES - Domain model:** Üzleti logika nem explicit → **Fázis 4 (2 hét)**

### Legfontosabb lépések (ha csak 1 hónapod van):

**1. hét:** TaskAuthorizationService (Security hole bezárása)  
**2-3. hét:** User Role Cache (10x gyorsabb query-k)  
**4. hét:** Tasks modul kiemelése (code quality)

### Várható eredmény (8 hét refaktor után):

✅ **Biztonságosabb** (resource-based authorization)  
✅ **10-20x gyorsabb** (cache, kevesebb HTTP)  
✅ **Könnyebben karbantartható** (tiszta modulok)  
✅ **Tesztelhető** (dependency injection, mock-ok)  
✅ **Skálázhatóbb** (SignalR, event-driven)  
✅ **Jobb UX** (real-time notifications)

---

## 📚 TOVÁBBI JAVASLATOK

### Event-Driven Architecture (hosszú távú)

```csharp
// Domain Events
public record TaskStatusChangedEvent(Guid TaskId, TaskStatus OldStatus, TaskStatus NewStatus) : IDomainEvent;

// Cross-module integration (loosely coupled)
public class AuditEventHandler : INotificationHandler<TaskStatusChangedEvent>
{
    public async Task Handle(TaskStatusChangedEvent evt, CancellationToken ct)
    {
        // Audit log automatikusan létrejön (nem kell explicit hívni)
        await _auditRepo.AddAsync(new AuditLogEntity
        {
            EntityType = "Task",
            EntityId = evt.TaskId,
            Action = $"Status changed: {evt.OldStatus} → {evt.NewStatus}"
        });
    }
}

// SignalR notification handler
public class TaskStatusNotificationHandler : INotificationHandler<TaskStatusChangedEvent>
{
    public async Task Handle(TaskStatusChangedEvent evt, CancellationToken ct)
    {
        await _hubContext.Clients
            .Group($"task_{evt.TaskId}")
            .SendAsync("StatusChanged", evt);
    }
}
```

### CQRS pattern erősítése

```csharp
// Separate Read Model (Dapper query)
public class TaskListReadModel
{
    public Guid Id { get; set; }
    public string TaskNumber { get; set; }
    public TaskStatus Status { get; set; }
    public string AssignedUserName { get; set; }  // Denormalized!
}

// Fast read query (no EF Core overhead)
public async Task<List<TaskListReadModel>> GetTaskListAsync()
{
    return await _dapperConnection.QueryAsync<TaskListReadModel>(
        "SELECT t.Id, t.TaskNumber, t.Status, u.FullName AS AssignedUserName " +
        "FROM Tasks t " +
        "LEFT JOIN Users u ON t.CurrentAssignedUserId = u.Id " +
        "WHERE t.Status != 'Archived'"
    );
}
```

## 🚀 HASZNÁLATI ÚTMUTATÓ - Hogyan használd ezt a dokumentumot?

### 📋 Prompt Sablonok (Másold be új conversation-be!)

#### **1. Konkrét probléma megoldásához**

```
Csatolom a FIDE backend architektúra elemzését. A "[PROBLÉMA SZÁM és CÍM]"
szekciót szeretném implementálni.

[MÁSOLD IDE AZ ARTIFACT TARTALMAT]

**Kérdéseim:**
1. [Konkrét kérdés 1]
2. [Konkrét kérdés 2]
3. [Konkrét kérdés 3]

**Jelenlegi kódom:** [illeszd be a releváns kódot]

**Kontextus:** [hol tartasz most, mi a legnagyobb fájdalompontod]
```

**Példa:**

```
Csatolom a FIDE backend architektúra elemzését. A "MEGOLDÁS 1: Authorization
Service bevezetése" szekciót szeretném implementálni.

[ARTIFACT]

**Kérdéseim:**
1. Hogyan implementáljam a TaskAuthorizationService-t, ha már van meglévő
   KeyCloakService dependency-m?
2. Mutass példát, hogyan migráljam át fokozatosan az EditTaskCommandHandler-t
3. Mi legyen a tesztelési stratégia?

**Jelenlegi kódom:** [EditTaskCommandHandler teljes kódja]

**Kontextus:** Security audit találta meg a hole-t, 1 hét van javításra.
```

---

#### **2. Részletes refaktor tervért (adott fázishoz)**

```
Csatolom a FIDE backend architektúra elemzését. Segíts a [FÁZIS NEVE]
implementációjában!

[ARTIFACT]

**Konkrét kérésem:**
- Készíts LÉPÉSRŐL-LÉPÉSRE útmutatót (checklist)
- Adj részletes kód példákat minden komponenshez
- Térj ki a migration stratégiára (production-ben törés nélkül)
- Adj unit test példákat

**Környezet:** [.NET verzió, EF Core verzió, KeyCloak verzió]
**Deadline:** [mikor kell kész lennie?]
```

**Példa:**

```
Csatolom a FIDE backend architektúra elemzését. Segíts a "Fázis 2: User Role
Cache" implementációjában!

[ARTIFACT]

**Konkrét kérésem:**
- Lépésről-lépésre checklist (mi a sorrend?)
- Teljes UserRoleSyncService implementáció
- Migration script példa (meglévő user-ek sync-je)
- Milyen cache stratégiát javasolsz? (Memory vs Redis)

**Környezet:** .NET 8, EF Core 8, KeyCloak 23
**Deadline:** 2 hét
```

---

#### **3. Security audit-hoz**

```
Csatolom a FIDE backend architektúra elemzését. Security audit-ot szeretnék
végezni a meglévő endpoint-jainkon.

[ARTIFACT]

**Feladat:**
1. Nézd át az alábbi Controller-eket, jelezd hol hiányzik authorization
2. Ellenőrizd, van-e resource-based authorization (nem csak permission check)
3. Javasolj konkrét javításokat minden endpoint-ra

**Controller kód:** [TaskController teljes kódja]

**Specifikus kérdés:** Van-e olyan endpoint, ahol a "Security Hole Példa"
szerinti exploit lehetséges?
```

---

#### **4. Performance optimalizáláshoz**

```
Csatolom a FIDE backend architektúra elemzését. A performance problémákat
szeretném megoldani.

[ARTIFACT]

**Specifikus kérések:**
- Mutasd meg a UserRoleSyncService teljes implementációját
- Hogyan tervezzem meg a migration script-et?
- Milyen cache stratégiát javasolsz? (Memory, Redis, Hybrid)
- Adj példát a refaktorált Query Handler-re

**Infrastruktúra:** [Redis elérhető? Hosting? Azure/AWS/On-prem?]
**Jelenlegi bottleneck-ek:** [Application Insights/monitoring adatok]
```

---

#### **5. SignalR real-time features-hez**

```
Csatolom a FIDE backend architektúra elemzését. SignalR real-time notification
rendszert szeretnék implementálni.

[ARTIFACT]

**Use case-ek:**
1. [pl. Task módosítás → real-time sync]
2. [pl. Status változás → notification]
3. [pl. Presence indicator - "ki nézi a task-ot?"]

**Kérdések:**
- Teljes SignalR Hub implementáció
- Frontend integration példák (React/Angular)
- Hogyan integráljam a meglévő Domain Event-ekkel?
- Scalability: több server esetén? (Azure SignalR Service?)

**Frontend tech stack:** [React? Angular? Vue?]
```

---

#### **6. Module refactoring tervezéshez**

```
Csatolom a FIDE backend architektúra elemzését. A TestDevelopment modult
szeretném szétbontani.

[ARTIFACT]

**Konkrét kérések:**
1. Milyen sorrendben bontsam szét? (függőségi fa)
2. Mutass példát az első almodul (Tasks/) kiemelésére
3. Hogyan kerüljem el a circular dependency-t?
4. Milyen interface-eket hozzak létre a modulok közötti kommunikációhoz?

**Jelenlegi struktúra:** [mappa struktúra, osztály lista]
**Cél:** [mi a legfontosabb use case, amit gyorsítani kell?]
```

---

#### **7. Testing stratégiához**

```
Csatolom a FIDE backend architektúra elemzését. Unit test-eket szeretnék
írni a refaktorált komponensekhez.

[ARTIFACT]

**Kérések:**
1. Adj példát TaskAuthorizationService unit test-jeire (különböző scenario-kra)
2. Hogyan mock-oljam a KeyCloak dependency-t?
3. Integration test példa: Authorization Handler tesztelése
4. Milyen test coverage-et célozzak? (70%? 80%?)

**Testing framework:** xUnit + FluentAssertions + Moq
**CI/CD:** [GitHub Actions? Azure DevOps?]
```

---

#### **8. Domain Model tisztításához**

```
Csatolom a FIDE backend architektúra elemzését. A Domain Model hiányosságokat
szeretném megoldani.

[ARTIFACT]

**Célom:**
1. TaskGroup explicit Aggregate Root-tá alakítása
2. TPH (Table-Per-Hierarchy) bevezetése User típusokra
3. Domain Events explicit modellezése

**Kérlek:**
- Mutasd meg a teljes TaskGroup Aggregate Root implementációt
- Adj EF Core migration példát a TPH bevezetésére
- Hogyan refaktoráljam a meglévő repository-kat?

**Jelenlegi entity-k:** [TaskEntity, TaskGroupEntity kód]
```

---

### 🎯 Tippek a legjobb eredményhez

#### **DO ✅**

- ✅ **Konkrét szekciót idézz**: "A 'MEGOLDÁS 2' szekciót szeretném implementálni"
- ✅ **Add meg a kontextust**: Dev/Staging/Prod? Mi a deadline?
- ✅ **Illeszd be a jelenlegi kódodat**: Így releváns, működő példákat kapsz
- ✅ **Kérdezz konkrétan**: "Hogyan?" "Milyen sorrendben?" "Mi a migration stratégia?"
- ✅ **Említsd a környezeted**: .NET verzió, infrastruktúra, team méret

#### **DON'T ❌**

- ❌ Ne kérdezd: "Implementáld nekem az egész refaktort" (túl nagy scope)
- ❌ Ne hagyd ki a kontextust (melyik fázisban vagy? mi a fájdalompont?)
- ❌ Ne próbálj 5 problémát egyszerre megoldani (FOKOZATOSAN!)
- ❌ Ne várj 100% kész production kódot (példák, amiken iterálni kell)

---

### 🔄 Iteratív használat (ajánlott workflow)

```
┌─────────────────────────────────────────────────────────┐
│                    REFAKTOR WORKFLOW                     │
└─────────────────────────────────────────────────────────┘

1️⃣ PRIORITÁS VÁLASZTÁS
   ├─ Olvasd el a "REFAKTOR PRIORITÁSOK" szekciót
   ├─ Válassz EGY fázist (pl. Fázis 1: TaskAuthorizationService)
   └─ Ne ugorj a 2. fázisra, amíg az 1. nincs kész!

2️⃣ RÉSZLETES TERV KÉRÉSE
   ├─ Új conversation: "Csatolom az artifact-ot, segíts Fázis 1-ben"
   ├─ Kérj checklist-et, kód példákat
   └─ Tisztázd a kérdéseket

3️⃣ IMPLEMENTÁCIÓ
   ├─ Írj egy komponenst (pl. TaskAuthorizationService)
   ├─ Írj hozzá unit test-et
   └─ Commit

4️⃣ TESTING & FEEDBACK
   ├─ Futtasd a test-eket
   ├─ Ha probléma van → új conversation: "Implementáltam, de XYZ probléma"
   └─ Iterálj

5️⃣ KÖVETKEZŐ KOMPONENS
   ├─ Ha az első kész → következő (pl. EditTaskCommandHandler)
   └─ Ismételd a 3-4. lépést

6️⃣ FÁZIS REVIEW
   ├─ Minden komponens kész? Code review
   ├─ Integration test (staging environment)
   └─ Ha OK → PRODUCTION deploy

7️⃣ KÖVETKEZŐ FÁZIS
   └─ Ugorj vissza az 1. lépéshez (Fázis 2)
```

---

### 📊 Progress Tracking (használd ezt a checklist-et!)

```markdown
## FIDE Refaktor Progress

### ✅ Fázis 1: Authorization Service (1 hét)

- [ ] TaskAuthorizationService interface + implementáció
- [ ] EditTaskCommandHandler refaktor
- [ ] TaskService cleanup (authorization kód törlése)
- [ ] Hiányzó [Authorize] attribute-ok hozzáadása
- [ ] Unit tesztek (70%+ coverage)
- [ ] Code review
- [ ] Staging deploy + testing
- [ ] Production deploy

### ⏳ Fázis 2: User Role Cache (2 hét)

- [ ] UserRoleEntity migration
- [ ] UserRoleSyncService implementáció
- [ ] UserRoleSyncMiddleware
- [ ] GetUsersByStatusQuery refaktor
- [ ] Background job (UserRoleSyncJob)
- [ ] Performance benchmark (előtte/utána)
- [ ] Production deploy

### 🔜 Fázis 3: Module Refactoring (3 hét)

- [ ] Tasks modul kiemelése
- [ ] TaskGroups modul
- [ ] Comments modul
- [ ] TestFiles modul
- [ ] TestVersions modul
- [ ] Structure modul

### 🔜 Fázis 4: Domain Model + SignalR (2 hét)

- [ ] TaskGroup Aggregate Root
- [ ] TPH User típusokra
- [ ] SignalR Hub
- [ ] Domain Events → SignalR
- [ ] Frontend integration
```

---

### 💡 Gyakori Problémák & Megoldások

#### **Probléma 1: "Túl sok változás egyszerre, nem tudom hol kezdjem"**

**Megoldás:** Kezd a Fázis 1-gyel (Authorization Service). Ez 1 hét, manageable, és NAGY hatása van (security + speed).

#### **Probléma 2: "A meglévő tesztek eltörnek refaktor közben"**

**Megoldás:**

- Először írd át a teszteket (mock az új dependency-ket)
- Utána refaktoráld a production kódot
- Red → Green → Refactor (TDD cycle)

#### **Probléma 3: "Production-ben nem merem átállítani"**

**Megoldás:** Feature flag + parallel deployment

```csharp
// Feature flag
if (_featureFlags.IsEnabled("UseNewAuthorizationService"))
{
    // Új kód (TaskAuthorizationService)
}
else
{
    // Régi kód (KeyCloak direct call)
}
```

#### **Probléma 4: "Nem tudom, melyik probléma a legfontosabb"**

**Megoldás:** Nézd meg a "📌 Gyors áttekintés" szekciót → 🔴 KRITIKUS problémák ELŐSZÖR!

#### **Probléma 5: "A team nem érti az új architektúrát"**

**Megoldás:**

- Internal tech talk (30 perc prezentáció)
- Pair programming session (vezess egy refaktort élőben)
- ADR (Architecture Decision Record) írása

---

### 📚 Kapcsolódó Dokumentációk

**Amit érdemes még elolvasni:**

- [Clean Architecture - Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Domain-Driven Design - Eric Evans](https://martinfowler.com/bliki/DomainDrivenDesign.html)
- [CQRS Pattern](https://martinfowler.com/bliki/CQRS.html)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [SignalR Documentation](https://learn.microsoft.com/en-us/aspnet/core/signalr/)

**FIDE-specifikus:**

- KeyCloak Admin Guide: [keycloak.org/docs](https://www.keycloak.org/docs/latest/server_admin/)
- EF Core Best Practices: [learn.microsoft.com/ef-core](https://learn.microsoft.com/en-us/ef/core/)

---

## 🎓 TANULSÁGOK (Ha újrakezdenéd a projektet...)

### Mit csinálnál másképp?

1. **Authorization:** Kezdettől fogva `IAuthorizationService` interface + resource-based check
2. **KeyCloak:** Cache-elt wrapper service (IIdentityProvider) az első naptól
3. **Modulok:** Max 15-20 osztály/modul (ne hagyj 78-ra nőni)
4. **Domain Model:** Aggregate Root-ok explicit (TaskGroup entity a kezdetektől)
5. **Testing:** Unit test minden új feature-hez (ne utólag!)
6. **Monitoring:** Application Insights/OpenTelemetry az elejétől (performance bottleneck-ek láthatók)

### Mit csinálnál ugyanúgy?

1. ✅ **CQRS + MediatR:** Jó választás, tiszta separation of concerns
2. ✅ **Repository Pattern:** Jó absztrakció (de generic repository hiányzik)
3. ✅ **EF Core:** Jó ORM választás (de több index kellene)
4. ✅ **KeyCloak:** Jó identity provider (de keverjük a cache-t!)

---

## 🎯 KÖVETKEZŐ LÉPÉSEK (Call to Action!)

### Ha MOST kezded:

1. 📖 **Olvasd el a "📌 Gyors áttekintés" szekciót** (5 perc)
2. 🔴 **Azonosítsd a legnagyobb fájdalompontot** (Security? Performance?)
3. 📋 **Válassz EGY prioritást** (Fázis 1 vagy Fázis 2)
4. 💬 **Új conversation:** Használd a prompt sablonokat!

### Ha már Fázis 1-ben vagy:

1. ✅ **Checklist:** Használd a "Progress Tracking" szekciót
2. 🧪 **Testing:** Írd meg a unit test-eket ELŐBB
3. 🚀 **Deploy:** Staging → testing → Production (fokozatosan!)

### Ha elakadtál:

1. 💬 **Feedback conversation:** "Implementáltam, de XYZ probléma"
2. 🤝 **Pair programming:** Kérj segítséget a team-től
3. 📚 **Dokumentáció:** Nézd meg a "Kapcsolódó Dokumentációk" szekciót

---

**Sok sikert a refaktorhoz! 🚀**

_Last updated: [Dátum]_  
_Version: 1.0_  
_Author: [Te + AI pair programming]_

.Include(u => u.CachedRoles) // ← Cached roles
.Include(u => u.UserLanguageLevels),
u => u.CachedRoles.Any(r => requiredRoles.Contains(r.RoleName)),
ct
);

    // Language filtering...
    return users.Select(u => u.ToUserForAssignmentDto(...));

}

````

**Performance:**
- **Előtte:** 500-1000ms (5-10 HTTP request)
- **Utána:** 20-50ms (1 DB query)

---

### 3. Resource-based Authorization Handler (ASP.NET Core native)

```csharp
// Requirement
public class TaskEditRequirement : IAuthorizationRequirement { }

// Handler
public class TaskEditAuthorizationHandler : AuthorizationHandler<TaskEditRequirement, TaskEntity>
{
    protected override Task HandleRequirementAsync(
        AuthorizationHandlerContext context,
        TaskEditRequirement requirement,
        TaskEntity resource)
    {
        var userId = context.User.FindFirst("sub")?.Value;

        // 1. Permission check (JWT-ből)
        var hasPermission = HasClientRole(context.User, "EditOwnTask") ||
                            HasClientRole(context.User, "TestDevelopment");

        if (!hasPermission)
        {
            context.Fail();
            return Task.CompletedTask;
        }

        // 2. Resource check
        var canEdit = CanUserEditTask(resource, userId, context.User);

        if (canEdit)
            context.Succeed(requirement);
        else
            context.Fail();

        return Task.CompletedTask;
    }

    private bool HasClientRole(ClaimsPrincipal user, string roleName)
    {
        var resourceAccess = user.FindFirst("resource_access");
        if (resourceAccess == null) return false;

        var value = JObject.Parse(resourceAccess.Value);
        return value.SelectToken($"$.fide-client.roles[?(@ == '{roleName}')]") != null;
    }

    private bool CanUserEditTask(TaskEntity task, string userId, ClaimsPrincipal user)
    {
        // Admin override
        if (HasClientRole(user, "TestDevelopment"))
            return true;

        // Status + Ownership checks
        return IsTaskEditable(task.Status) && IsUserAssigned(task, userId);
    }
}
````

**Program.cs regisztráció:**

```csharp
builder.Services.AddAuthorizationBuilder()
    .AddPolicy("CanEditTask", policy =>
        policy.Requirements.Add(new TaskEditRequirement()));

builder.Services.AddScoped<IAuthorizationHandler, TaskEditAuthorizationHandler>();
```

**Command Handler használat:**

```csharp
var authResult = await _authzService.AuthorizeAsync(
    _httpContext.HttpContext.User,
    task,
    new TaskEditRequirement()
);

if (!authResult.Succeeded)
    return Result.Fail("Unauthorized");
```

---

## REFAKTOR PRIORITÁSOK

### Fázis 1: Quick Wins (1 hét)

1. ✅ **TaskAuthorizationService** létrehozása
2. ✅ **EditTaskCommandHandler** refaktor (KeyCloak hívás kihelyezése)
3. ✅ **TaskService cleanup** (30+ sor authorization kód törlése)

### Fázis 2: User Role Cache (2 hét)

4. ✅ **UserRoleEntity** + EF Core migration
5. ✅ **UserRoleSyncService** implementáció
6. ✅ **UserRoleSyncMiddleware** (login-kor sync)
7. ✅ **GetUsersByStatusQuery** refaktor

### Fázis 3: Module Refactoring (3 hét)

8. ✅ **TestDevelopment modul** szétbontása (Tasks, TaskGroups, Comments, stb.)
9. ✅ **Users modul** szétbontása
10. ✅ **Generic Repository** bevezetése (DRY)

### Fázis 4: Domain Model (2 hét)

11. ✅ **TaskGroup** explicit Aggregate Root
12. ✅ **TPH bevezetése** BaseUserEntity-re
13. ✅ **Domain Events** explicit modellezése

### Fázis 5: Performance (1 hét)

14. ✅ **IMemoryCache** hozzáadása KeyCloak hívásokhoz
15. ✅ **Background Job** (periodic user role sync)

---

## KRITIKUS SECURITY JAVÍTÁSOK (AZONNAL!)

### 1. Hiányzó [Authorize] attribute-ok

```csharp
// ELŐTTE (VESZÉLYES):
[HttpGet("Group/{taskGroupId}/translatable-languages")]
public async Task<ActionResult<TranslatableLanguagesDto>> GetTranslatableLanguages(...)

// UTÁNA:
[Authorize(Policy = Scopes.TaskObservation)]
[HttpGet("Group/{taskGroupId}/translatable-languages")]
public async Task<ActionResult<TranslatableLanguagesDto>> GetTranslatableLanguages(...)
```

### 2. Resource-based authorization hiánya

**Jelenlegi:** Bárki szerkeszthet bármely task-ot, ha van `EditOwnTask` permission-je
**Javítás:** TaskAuthorizationService + resource check minden Command Handler-ben

---

## MÉRŐSZÁMOK

### Cél metrikák:

- **Modul méret:** Max 15-20 osztály/modul
- **Coupling:** Max 5-6 másik modulra hivatkozás
- **Test coverage:** Min 70% unit test lefedettség
- **Query latency:** Max 100ms (99th percentile)
- **Authorization check:** Max 50ms

### Jelenlegi vs Cél:

| Metrika                   | Jelenlegi  | Cél               |
| ------------------------- | ---------- | ----------------- |
| TestDevelopment osztályok | 78         | 15-20 (6 almodul) |
| KeyCloak hívások/request  | 5-10       | 0 (cache)         |
| Authorization latency     | 200-500ms  | 10-50ms           |
| User query latency        | 500-1000ms | 20-50ms           |

---

## TOVÁBBI JAVASLATOK

### Event-Driven Architecture bevezetése

```csharp
public class TaskStatusChangedEvent : IDomainEvent
{
    public Guid TaskId { get; set; }
    public TaskStatus OldStatus { get; set; }
    public TaskStatus NewStatus { get; set; }
}

// Cross-module integration
public class AuditEventHandler : INotificationHandler<TaskStatusChangedEvent>
{
    public async Task Handle(TaskStatusChangedEvent evt, CancellationToken ct)
    {
        // Audit log létrehozása (loosely coupled)
    }
}
```

### CQRS pattern erősítése

- Read modellek (Query) elkülönítése Write modellektől
- Dapper használata összetett lekérdezésekhez
- Separate DB (vagy schema) read/write-ra

---

## ÖSSZEFOGLALÁS

**Legnagyobb problémák:**

1. 🔴 **Security hole:** Nincs resource-based authorization
2. 🔴 **Performance:** KeyCloak hívások minden request-nél
3. 🟠 **Coupling:** KeyCloak integráció szétszórva
4. 🟠 **Monolith modulok:** TestDevelopment (78 osztály)
5. 🟡 **Domain model:** TaskGroup nem explicit Aggregate Root

**Legfontosabb lépések:**

1. ✅ **TaskAuthorizationService** (azonnal)
2. ✅ **User Role Cache** (1-2 hét)
3. ✅ **Module refactoring** (1 hónap)
4. ✅ **Domain model tisztítása** (2 hét)

**Várható eredmény:**

- ✅ Biztonságosabb (resource-based authorization)
- ✅ 10x gyorsabb (cache, kevesebb HTTP)
- ✅ Könnyebben karbantartható (tiszta separation of concerns)
- ✅ Tesztelhető (dependency injection, mock-olható services)
