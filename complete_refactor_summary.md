# Fide Test Development - Complete Domain Refactoring Summary

## Executive Summary

Teljes Domain-Driven Design (DDD) refaktorálás egy nyelvvizsga központ teszt fejlesztő rendszeréhez. A refaktorálás célja:
- Aggregate Root pattern bevezetése
- Nyelvkezelés egyszerűsítése (TranslatedText Value Object)
- Workflow explicit kezelése (State Machine)
- Domain Events bevezetése
- Table-Per-Type (TPT) inheritance Field és Answer típusokhoz

**Időigény**: 4-5 hét (25-35 munkanap)

---

## Business Domain Overview

### Főbb szereplők:
- **Test Developer**: Feladatokat review-ol, scenario-kat választ
- **Item Writer**: Feladatokat készít (DE nyelven)
- **Translator**: FR/IT fordításokat készít
- **Reviewer**: Review-ol minden szakaszban
- **Candidate**: Vizsgát tesz
- **Examiner**: Vizsgáztat
- **Assessor**: Javít

### Workflow áttekintés:
1. **Task létrehozás**: Test Developer modul-t assignol Item Writer-nek → Draft Task jön létre (DE)
2. **Task fejlesztés**: Item Writer dolgozik → InReview státusz
3. **Review**: Test Developer review-ol → jóváhagyás VAGY InRevision (vissza Item Writer-hez)
4. **Translation**: Jóváhagyás után FR/IT task-ok létrejönnek → Translator-ok dolgoznak
5. **Translation Review**: Lefordított task-ok review-ra kerülnek
6. **Testing**: Mindhárom nyelv kész → InTesting státusz
7. **Release**: Teszt után → Released (immutable!)
8. **Archive**: Már nem használt tesztek

### Hierarchy:
```
TestVersion (v1, v2, v3...)
└── Module (Module 1, Module 2, Part 1, Part 2...)
    └── TaskGroup (scenario + 3 nyelv: DE, FR, IT)
        └── Task (egy nyelv)
            └── Field (situationDescription, items, image, stb.)
                └── Item (konkrét kérdés)
                    └── ItemAnswer (helyes válasz config)
```

### Scenario Catalog (külön aggregate):
```
Domain (pl. "Orvos")
└── ActionField (pl. "Orvosi vizsgálat")
    └── Scenario (pl. "Torokfájással háziorvoshoz")
```

---

## Identified Problems

### 1. Anemic Domain Model
- Entitások csak adattárolók
- Business logic szétszórva service-ekben
- Nehéz follow-olni a business rule-okat

### 2. Nyelvkezelés ad-hoc
- GroupId alapú csoportosítás
- 3 külön rekord (DE, FR, IT) minden entitáshoz
- `IGroupableEntity` interface komplexitás

### 3. Workflow implicit
- Task státuszok + 3 külön user property (ItemWriter, Translator, Reviewer)
- Nehéz validálni state transition-öket
- CurrentAssignedUser sync probléma

### 4. Field Types problema
- Egy FieldEntity 15+ nullable property
- Type discrimination string-gel
- Nehéz type-safe-en dolgozni

### 5. Nincs Answer kezelés
- Helyes válaszok, scoring hiányzik
- Alternatívák kezelése nincs

### 6. Module nem entitás
- ModuleId és ModuleNumber van, de nincs ModuleEntity
- Hierarchia nem explicit

### 7. Verziókezelés implicit
- TestVersion "revision" fogalom nem explicit
- Immutability nincs enforce-olva

---

## Proposed Solution

### 1. Aggregate Roots

#### TestVersion Aggregate (FŐ)
**Root**: `TestVersionEntity`
**Határai**: TestVersion → Module → TaskGroup → Task → Field → Item → ItemAnswer

**Invariánsok**:
- Released TestVersion immutable
- Minden Task-nak van assigned user-e
- Task státusz átmenetek validálása
- Nyelvek konzisztenciája (DE/FR/IT)
- Module-ok és Task-ok konzisztenciája

#### ScenarioCatalog Aggregate
**Root**: `ScenarioCatalogEntity` (vagy kezdetben csak Domain)
**Határai**: Domain → ActionField → Scenario (mind TranslatedText-tel)

**Invariánsok**:
- Minden entitás 3 nyelven létezik (TranslatedText)
- Hierarchia konzisztenciája

#### Order Aggregate
**Root**: `OrderEntity`
**Határai**: Order → Candidate enrollments

**Invariánsok**:
- Order csak Released TestVersion-höz köthető
- Candidate validáció

#### User Aggregate (megtartva)
**Root**: `BaseUserEntity`
**Határai**: User → Profiles → Permissions → Groups

---

## Key Refactorings

### 1. TranslatedText Value Object

**Előtt**:
```csharp
public class ScenarioEntity : IGroupableEntity
{
    public Guid Id { get; set; }
    public Guid GroupId { get; set; }
    public Language Language { get; set; }
    public string ScenarioText { get; set; }
}

// 3 rekord:
// - Id=1, GroupId=X, Language=DE, Text="German text"
// - Id=2, GroupId=X, Language=FR, Text="French text"
// - Id=3, GroupId=X, Language=IT, Text="Italian text"
```

**Utána**:
```csharp
public class ScenarioEntity
{
    public Guid Id { get; set; }
    public TranslatedText ScenarioText { get; set; } // DE, FR, IT együtt
}

public class TranslatedText // Value Object
{
    public string DE { get; private set; }
    public string? FR { get; private set; }
    public string? IT { get; private set; }
    
    public string GetTranslation(Language lang) => lang switch
    {
        Language.DE => DE,
        Language.FR => FR ?? DE,
        Language.IT => IT ?? DE,
        _ => DE
    };
}

// 1 rekord:
// - Id=1, ScenarioText_DE="...", ScenarioText_FR="...", ScenarioText_IT="..."
```

**Előnyök**:
- ❌ Nincs GroupId
- ❌ Nincs IGroupableEntity
- ✅ 1 rekord 3 helyett
- ✅ Type-safe language access
- ✅ Egyszerűbb query-k

### 2. TaskEntity Workflow State Machine

**Előtt**:
```csharp
public class TaskEntity
{
    public TaskStatus Status { get; set; }
    public Guid CurrentAssignedUserId { get; set; }
    public Guid? ItemWriterId { get; set; }
    public Guid? TranslatorId { get; set; }
    public Guid? ReviewerId { get; set; }
}

// Service-ben:
public async Task UpdateStatus(Guid taskId, TaskStatus newStatus)
{
    var task = await repo.Get(taskId);
    
    // Business logic here!
    if (task.Status != TaskStatus.Draft)
        throw new Exception("Can only submit draft");
    
    task.Status = newStatus;
    task.ReviewerId = reviewerId;
    await repo.Update(task);
}
```

**Utána**:
```csharp
public class TaskEntity : EntityBase
{
    public TaskStatus Status { get; private set; }
    public TaskAssignment CurrentAssignment { get; private set; } // VO
    public Guid ItemWriterId { get; private set; }
    public Guid? TranslatorId { get; private set; }
    public Guid? ReviewerId { get; private set; }
    
    // Domain methods with business rules!
    public void SubmitForReview(Guid reviewerId, Guid submittedBy)
    {
        ValidateStatusTransition(TaskStatus.Draft, TaskStatus.InReview);
        ValidateCurrentUser(submittedBy);
        
        Status = TaskStatus.InReview;
        ReviewerId = reviewerId;
        CurrentAssignment = new TaskAssignment(reviewerId, TaskRole.Reviewer);
        
        RaiseDomainEvent(new TaskSubmittedForReviewEvent(...));
    }
    
    public void SendBackForRevision(Guid reviewerId) { ... }
    public void ApproveForTranslation(Guid userId) { ... }
    // ... more workflow methods
}

public class TaskAssignment // Value Object
{
    public Guid UserId { get; private set; }
    public TaskRole Role { get; private set; }
    public DateTimeOffset AssignedAt { get; private set; }
}
```

**Előnyök**:
- ✅ Business logic a domain-ben
- ✅ State transition validáció
- ✅ Explicit role assignment
- ✅ Domain events
- ✅ Könnyebb tesztelni

### 3. TestVersion Versioning

**Előtt**:
```csharp
public class TestVersionEntity
{
    public Guid Id { get; set; }
    public string VersionName { get; set; }
    // Revision koncepció implicit
}
```

**Utána**:
```csharp
public class TestVersionEntity : EntityBase
{
    public int Version { get; private set; } = 1;
    public Guid? PreviousVersionId { get; private set; }
    public TestVersionEntity? PreviousVersion { get; set; }
    public TestVersionStatus Status { get; private set; }
    public DateTimeOffset? ReleasedAt { get; private set; }
    
    public TestVersionEntity CreateRevision(Guid userId)
    {
        if (Status != TestVersionStatus.Released)
            throw new InvalidOperationException("Can only revise released versions");
        
        return new TestVersionEntity
        {
            Version = this.Version + 1,
            PreviousVersionId = this.Id,
            Status = TestVersionStatus.Draft
        };
    }
    
    public void Release(Guid userId)
    {
        ValidateStatusTransition(TestVersionStatus.InReview, TestVersionStatus.Released);
        ValidateAllTasksReleased();
        
        Status = TestVersionStatus.Released;
        ReleasedAt = DateTimeOffset.UtcNow;
        ReleasedByUserId = userId;
        
        RaiseDomainEvent(new TestVersionReleasedEvent(...));
    }
    
    public bool IsImmutable => Status is TestVersionStatus.Released or TestVersionStatus.Archived;
}
```

**Előnyök**:
- ✅ Revision chain explicit
- ✅ Immutability enforce-olva
- ✅ Version tracking
- ✅ Release validation

### 4. Field Types - TPT Hierarchy

**Előtt**:
```csharp
public class FieldEntity
{
    public string FieldType { get; set; } // string!
    
    // Minden típushoz nullable property...
    public string? SituationDescription { get; set; }
    public string? InputText { get; set; }
    public string? ConstructDescription { get; set; }
    public string? InstructionInput { get; set; }
    public string? Introduction { get; set; }
    public string? ResponseText { get; set; }
    public string? Title { get; set; }
    public string? FileDescription { get; set; }
    // ... 10+ property
}
```

**Utána**:
```csharp
public abstract class FieldEntity
{
    public Guid Id { get; set; }
    public Guid TaskId { get; set; }
    public int Position { get; set; }
    public Language Language { get; set; }
    
    public abstract string GetFieldType();
}

public class SituationDescriptionField : FieldEntity
{
    public required string SituationDescription { get; set; }
    public override string GetFieldType() => "situationDescription";
}

public class ItemsField : FieldEntity
{
    public ICollection<ItemEntity> Items { get; set; } = [];
    public LayoutType? Layout { get; set; }
    public override string GetFieldType() => "items";
}

// ... 14 total field types
```

**EF Configuration**:
```csharp
modelBuilder.Entity<FieldEntity>()
    .ToTable("Fields")
    .HasKey(f => f.Id);

modelBuilder.Entity<SituationDescriptionField>()
    .ToTable("Fields_SituationDescription");

modelBuilder.Entity<ItemsField>()
    .ToTable("Fields_Items");
```

**Előnyök**:
- ✅ Type-safe
- ✅ Nincs null property explosion
- ✅ Könnyebb field-specific logic
- ✅ Clearer intent

### 5. Item Answer System

**Új feature!**
```csharp
public abstract class ItemAnswerEntity
{
    public Guid Id { get; set; }
    public Guid ItemId { get; set; }
    public ItemEntity Item { get; set; }
    public decimal MaxPoints { get; set; }
    
    public abstract bool IsCorrect(string candidateResponse);
    public abstract decimal CalculatePoints(string candidateResponse);
}

public class MultipleChoiceAnswerEntity : ItemAnswerEntity
{
    public List<ChoiceOption> Choices { get; set; }
    public string CorrectChoiceId { get; set; }
    
    public override bool IsCorrect(string response)
    {
        return response?.Trim().Equals(CorrectChoiceId, 
            StringComparison.OrdinalIgnoreCase) ?? false;
    }
}

public class TextInputAnswerEntity : ItemAnswerEntity
{
    public string CorrectAnswer { get; set; }
    public List<string> AcceptableAnswers { get; set; } = [];
    public TextMatchStrategy MatchStrategy { get; set; }
    public bool CaseSensitive { get; set; }
    
    public override bool IsCorrect(string response) { ... }
}

public class OpenEndedAnswerEntity : ItemAnswerEntity
{
    public string AssessmentRubric { get; set; }
    public List<string> SampleAnswers { get; set; } = [];
    
    public override bool IsCorrect(string response)
    {
        // Cannot auto-grade, requires manual assessment
        return ValidateBasicRequirements(response);
    }
}
```

**ItemEntity kapcsolat**:
```csharp
public class ItemEntity
{
    public Guid Id { get; set; }
    public string ItemNumber { get; set; }
    
    // Answer configuration
    public ItemAnswerEntity? Answer { get; set; }
    
    // Alternative handling
    public Guid? AlternativeGroupId { get; set; }
    public bool IsSelected { get; set; }
}
```

### 6. Module Entity

**Előtt**: ModuleId és ModuleNumber property-k szétszórva

**Utána**:
```csharp
public class ModuleEntity
{
    public Guid Id { get; set; }
    public string ModuleNumber { get; set; } // "Module 1", "Part 1"
    public string ModuleName { get; set; }
    public ModuleType Type { get; set; } // Reading, Writing, Speaking
    public Level Level { get; set; } // A1, A2, B1...
    
    public Guid TestVersionId { get; set; }
    public TestVersionEntity TestVersion { get; set; }
    
    public ICollection<TaskGroupEntity> TaskGroups { get; set; } = [];
}
```

**Hierarchy**:
```
TestVersion
└── Module ← ÚJ!
    └── TaskGroup
        └── Task
```

### 7. Domain Events

**Infrastructure**:
```csharp
public interface IDomainEvent : INotification
{
    DateTimeOffset OccurredOn { get; }
}

public abstract class EntityBase
{
    private List<IDomainEvent> _domainEvents = new();
    
    public IReadOnlyCollection<IDomainEvent> DomainEvents => _domainEvents;
    
    protected void RaiseDomainEvent(IDomainEvent evt)
    {
        _domainEvents.Add(evt);
    }
    
    public void ClearDomainEvents() => _domainEvents.Clear();
}
```

**Events példák**:
```csharp
public class TaskSubmittedForReviewEvent : DomainEventBase
{
    public Guid TaskId { get; }
    public Guid SubmittedByUserId { get; }
    public Guid ReviewerId { get; }
}

public class TaskApprovedForTranslationEvent : DomainEventBase
{
    public Guid TaskId { get; }
    public Guid TaskGroupId { get; }
    // Handler creates FR/IT tasks!
}

public class TestVersionReleasedEvent : DomainEventBase
{
    public Guid TestVersionId { get; }
    public Guid ReleasedByUserId { get; }
}
```

**Handler példa**:
```csharp
public class TaskApprovedForTranslationHandler 
    : INotificationHandler<TaskApprovedForTranslationEvent>
{
    public async Task Handle(TaskApprovedForTranslationEvent evt, CancellationToken ct)
    {
        var deTask = await taskRepo.GetWithAllData(evt.TaskId, ct);
        
        // Create FR task
        var frTask = TaskEntity.CreateTranslationFrom(deTask, Language.FR, translatorId);
        await taskRepo.Add(frTask, ct);
        
        // Create IT task
        var itTask = TaskEntity.CreateTranslationFrom(deTask, Language.IT, translatorId);
        await taskRepo.Add(itTask, ct);
    }
}
```

**Automatic dispatch**:
```csharp
public class DomainEventDispatcherInterceptor : SaveChangesInterceptor
{
    public override async ValueTask<InterceptionResult<int>> SavingChangesAsync(...)
    {
        var entities = context.ChangeTracker
            .Entries<EntityBase>()
            .Where(e => e.Entity.DomainEvents.Any())
            .Select(e => e.Entity)
            .ToList();
        
        var events = entities.SelectMany(e => e.DomainEvents).ToList();
        entities.ForEach(e => e.ClearDomainEvents());
        
        foreach (var evt in events)
            await mediator.Publish(evt, ct);
        
        return await base.SavingChangesAsync(...);
    }
}
```

---

## Service Layer Refactoring

### Anti-Pattern (Előtt):
```csharp
// ❌ Business logic az application service-ben
public class TaskService
{
    public async Task SubmitForReview(Guid taskId, Guid reviewerId)
    {
        var task = await repo.Get(taskId);
        
        // Business logic - BAD!
        if (task.Status != TaskStatus.Draft)
            throw new Exception();
        
        task.Status = TaskStatus.InReview;
        task.ReviewerId = reviewerId;
        task.CurrentAssignedUserId = reviewerId;
        
        await repo.Update(task);
    }
}
```

### Pattern (Utána):
```csharp
// ✅ Business logic a domain-ben
public class TaskApplicationService
{
    public async Task SubmitForReviewAsync(
        Guid taskId, 
        Guid reviewerId, 
        Guid userId, 
        CancellationToken ct)
    {
        // 1. Load aggregate
        var task = await taskRepo.GetWithAllData(taskId, ct);
        
        // 2. Authorization
        if (!await authService.CanEditTask(task, userId, ct))
            throw new UnauthorizedException();
        
        // 3. Domain method (ALL business logic here!)
        task.SubmitForReview(reviewerId, userId);
        
        // 4. Persist
        await taskRepo.Update(task, ct);
        
        // 5. Events dispatched automatically by interceptor
    }
}

// Domain
public class TaskEntity : EntityBase
{
    public void SubmitForReview(Guid reviewerId, Guid submittedBy)
    {
        // Business rules
        ValidateStatusTransition(TaskStatus.Draft, TaskStatus.InReview);
        ValidateCurrentUser(submittedBy);
        
        // State change
        Status = TaskStatus.InReview;
        ReviewerId = reviewerId;
        CurrentAssignment = new TaskAssignment(reviewerId, TaskRole.Reviewer);
        UpdatedOn = DateTimeOffset.UtcNow;
        
        // Event
        RaiseDomainEvent(new TaskSubmittedForReviewEvent(Id, submittedBy, reviewerId));
    }
}
```

### Service felelősségek:

#### Application Service
- ✅ Input validáció (DTO szintű)
- ✅ Authorization
- ✅ DTO ↔ Entity mapping
- ✅ Repository orchestration
- ✅ Transaction management
- ❌ Business logic

#### Domain Service
- ✅ Multi-aggregate operations
- ✅ Domain logic that doesn't fit in single aggregate
- ✅ Complex calculations
- Példa: `TestVersionRevisionService` (deep copy across aggregates)

#### Query Service
- ✅ Read-only operations
- ✅ DTO projection
- ✅ Direkt DbContext query (bypass aggregates)
- ✅ Performance optimized reads

---

## Migration Strategy

### Fázis 1: Foundation (2-3 nap)
1. TranslatedText Value Object
2. ModuleEntity
3. Új enum-ok
4. Unit tesztek

### Fázis 2: Scenario Catalog (3-4 nap)
1. Domain/ActionField/Scenario refaktor
2. Migration szkript adatokhoz
3. GroupId törlése
4. EF Configuration

### Fázis 3: Task Workflow + Events (5-6 nap)
1. TaskAssignment VO
2. EntityBase + Domain Events
3. Workflow methods implementálása
4. Domain Event Handlers
5. Migration szkript

### Fázis 4: TestVersion Versioning (3-4 nap)
1. Version tracking
2. CreateRevision() + deep copy
3. TestVersionRevisionService
4. Integration tesztek

### Fázis 5: Module Integration (2-3 nap)
1. Module Entity integrálása
2. TaskGroup → Module kapcsolat
3. Migration

### Fázis 6: Field TPT (4-5 nap)
1. 14 Field type class
2. EF TPT configuration
3. Migration
4. Factory pattern field creation

### Fázis 7: Answer System (3-4 nap)
1. ItemAnswerEntity hierarchy
2. 5 answer type implementation
3. EF TPT configuration
4. Scoring logic

### Fázis 8: Event Handlers (2-3 nap)
1. Translation creation handler
2. Alternative selection handler
3. Notification handlers
4. Audit handlers

### Fázis 9: Service Refactor (3-4 nap)
1. TaskApplicationService refactor
2. TaskQueryService extraction
3. Domain Service creation
4. Controller updates

### Fázis 10: Cleanup (2-3 nap)
1. Régi kód törlése
2. Migration cleanup
3. Full test suite
4. Code review

**Összesen**: 25-35 munkanap

---

## Code Organization

```
Fide.Application/
├── Entities/
│   ├── Common/
│   │   ├── EntityBase.cs
│   │   └── IDomainEvent.cs
│   ├── TestDevelopment/
│   │   ├── TestVersionEntity.cs (Aggregate Root)
│   │   ├── ModuleEntity.cs
│   │   ├── TaskGroupEntity.cs
│   │   ├── TaskEntity.cs (Aggregate Root)
│   │   ├── DomainEntity.cs (Aggregate Root)
│   │   ├── ActionFieldEntity.cs
│   │   ├── ScenarioEntity.cs
│   │   ├── ItemEntity.cs
│   │   ├── Fields/
│   │   │   ├── FieldEntity.cs (base)
│   │   │   ├── SituationDescriptionField.cs
│   │   │   ├── ItemsField.cs
│   │   │   └── ... (14 field types)
│   │   ├── Answers/
│   │   │   ├── ItemAnswerEntity.cs (base)
│   │   │   ├── MultipleChoiceAnswerEntity.cs
│   │   │   ├── TextInputAnswerEntity.cs
│   │   │   └── ... (5 answer types)
│   │   ├── ValueObjects/
│   │   │   ├── TranslatedText.cs
│   │   │   └── TaskAssignment.cs
│   │   └── Events/
│   │       ├── TaskSubmittedForReviewEvent.cs
│   │       ├── TaskApprovedForTranslationEvent.cs
│   │       └── ... (10+ events)
│   └── Users/
│       └── BaseUserEntity.cs (Aggregate Root)
├── Services/
│   ├── Application/
│   │   ├── TaskApplicationService.cs
│   │   ├── TestVersionApplicationService.cs
│   │   └── ...
│   ├── Domain/
│   │   ├── TestVersionRevisionService.cs
│   │   └── TaskTranslationCoordinatorService.cs
│   └── Query/
│       ├── TaskQueryService.cs
│       └── TestVersionQueryService.cs
├── EventHandlers/
│   └── TestDevelopment/
│       ├── TaskApprovedForTranslationHandler.cs
│       ├── ItemAlternativeSelectedHandler.cs
│       └── ...
├── Repositories/
│   └── ... (unchanged)
└── Infrastructure/
    └── Persistence/
        ├── FideDbContext.cs
        ├── DomainEventDispatcherInterceptor.cs
        └── AuditSaveChangesInterceptor.cs
```

---

## Testing Strategy

### Unit Tests (Domain Logic)
```csharp
[Fact]
public void TaskEntity_SubmitForReview_ChangesStatusAndAssignment()
{
    // Arrange
    var task = TaskEntity.CreateDraft("T1", Language.DE, itemWriterId, taskGroupId);
    var reviewerId = Guid.NewGuid();
    
    // Act
    task.SubmitForReview(reviewerId, itemWriterId);
    
    // Assert
    Assert.Equal(TaskStatus.InReview, task.Status);
    Assert.Equal(reviewerId, task.CurrentAssignment.UserId);
    Assert.Equal(TaskRole.Reviewer, task.CurrentAssignment.Role);
    Assert.Single(task.DomainEvents);
}

[Fact]
public void TaskEntity_SubmitForReview_ThrowsWhenNotDraft()
{
    // Arrange
    var task = TaskEntity.CreateDraft(...);
    task.SubmitForReview(reviewerId, userId);
    
    // Act & Assert
    Assert.Throws<InvalidOperationException>(() => 
        task.SubmitForReview(reviewerId, userId));
}
```

### Integration Tests
```csharp
[Fact]
public async Task TestVersionRevisionService_CreatesNewVersion()
{
    // Arrange
    using var context = CreateTestContext();
    var service = new TestVersionRevisionService(context);
    var original = await CreateReleasedTestVersion(context);
    
    // Act
    var revision = await service.CreateRevision(original.Id, userId, ct);
    
    // Assert
    Assert.Equal(original.Version + 1, revision.Version);
    Assert.Equal(original.Id, revision.PreviousVersionId);
    Assert.Equal(TestVersionStatus.Draft, revision.Status);
    Assert.Equal(original.Modules.Count, revision.Modules.Count);
}
```

### Event Handler Tests
```csharp
[Fact]
public async Task TaskApprovedForTranslationHandler_CreatesFRAndITTasks()
{
    // Arrange
    var evt = new TaskApprovedForTranslationEvent(deTaskId, taskGroupId, userId);
    var handler = new TaskApprovedForTranslationHandler(context, logger);
    
    // Act
    await handler.Handle(evt, ct);
    
    // Assert
    var tasks = await context.Tasks.Where(t => t.TaskGroupId == taskGroupId).ToListAsync();
    Assert.Equal(3, tasks.Count); // DE, FR, IT
    Assert.Contains(tasks, t => t.Language == Language.FR);
    Assert.Contains(tasks, t => t.Language == Language.IT);
}
```

---

## Benefits Summary

### Code Quality
- ✅ Clear separation of concerns
- ✅ Business logic in domain
- ✅ Type-safe operations
- ✅ Easier to test
- ✅ Explicit invariants

### Maintainability
- ✅ Changes localized to aggregates
- ✅ Domain events decouple operations
- ✅ Clear boundaries
- ✅ Self-documenting code

### Business Alignment
- ✅ Code matches business concepts
- ✅ Ubiquitous language
- ✅ Workflow explicit
- ✅ Rules enforceable

### Performance
- ✅ Query optimization (Query Services)
- ✅ Lazy loading where appropriate
- ✅ Efficient change tracking

---

## Key Decisions

### 1. TPT vs TPC vs TPH for Field/Answer types
**Decision**: TPT (Table Per Type)
**Reason**: 
- Type safety
- Clear schema
- Easy to add new types
- ~14-15 tables acceptable for this domain

### 2. CQRS vs Traditional Services
**Decision**: Start with traditional, migrate to CQRS later
**Reason**:
- Phased approach
- Team familiarity
- Can add later without major refactor

### 3. Domain Events vs Integration Events
**Decision**: Start with Domain Events only
**Reason**:
- Internal communication first
- Add Integration Events for external systems later

### 4. Audit Strategy
**Decision**: Keep current interceptor approach
**Reason**:
- Working well
- Separate concern from domain
- Can be extended with events later

---

## Anti-Patterns to Avoid

### ❌ Anemic Domain Model
```csharp
// BAD
public class TaskEntity
{
    public TaskStatus Status { get; set; } // public setter!
}

// Service
task.Status = TaskStatus.InReview; // anyone can change
```

### ❌ Business Logic in Service
```csharp
// BAD
public class TaskService
{
    public async Task Submit(Guid id)
    {
        var task = await repo.Get(id);
        
        // Business logic here = BAD!
        if (task.Status != TaskStatus.Draft)
            throw new Exception();
        
        task.Status = TaskStatus.InReview;
        await repo.Update(task);
    }
}
```

### ❌ Aggregate Root Bypass
```csharp
// BAD - modifying child entity directly
var item = await itemRepo.Get(itemId);
item.ItemText = "changed"; // bypasses Task aggregate!
await itemRepo.Update(item);

// GOOD - through aggregate root
var task = await taskRepo.GetWithItems(taskId);
task.UpdateItemText(itemId, "changed"); // validates business rules
await taskRepo.Update(task);
```

### ❌ Fat Entities
```csharp
// BAD - entity doing infrastructure work
public class TaskEntity
{
    public async Task SendEmailToReviewer()
    {
        await emailService.Send(...); // NO!
    }
}

// GOOD - entity raises event, handler sends email
public class TaskEntity
{
    public void SubmitForReview(Guid reviewerId, Guid userId)
    {
        // ... business logic
        RaiseDomainEvent(new TaskSubmittedForReviewEvent(...));
    }
}

// Handler
public class TaskSubmittedForReviewHandler : INotificationHandler<...>
{
    public async Task Handle(TaskSubmittedForReviewEvent evt, CancellationToken ct)
    {
        await emailService.SendReviewNotification(...);
    }
}
```

### ❌ Cross-Aggregate Transactions
```csharp
// BAD - modifying multiple aggregates in one transaction
var testVersion = await repo.GetTestVersion(id);
var order = await repo.GetOrder(orderId);

testVersion.Release();
order.ActivateForTesting();

await unitOfWork.Commit(); // risky!

// GOOD - use domain events for consistency
var testVersion = await repo.GetTestVersion(id);
testVersion.Release(); // raises TestVersionReleasedEvent
await repo.Update(testVersion);

// Event handler updates Order separately
public class TestVersionReleasedHandler
{
    public async Task Handle(TestVersionReleasedEvent evt)
    {
        var orders = await orderRepo.GetByTestVersion(evt.TestVersionId);
        foreach (var order in orders)
        {
            order.ActivateForTesting();
            await orderRepo.Update(order);
        }
    }
}
```

---

## Patterns Used

### 1. Aggregate Root Pattern
Ensures consistency within aggregate boundaries. All changes go through root.

### 2. Value Object Pattern
Immutable objects representing concepts (TranslatedText, TaskAssignment).

### 3. Domain Events Pattern
Decouples aggregates and enables eventual consistency.

### 4. State Machine Pattern
Explicit state transitions with validation (TaskEntity workflow).

### 5. Repository Pattern
Abstracts data access, works with aggregate roots.

### 6. Factory Pattern
Creates complex entities consistently (TaskEntity.CreateDraft()).

### 7. Specification Pattern (future)
Encapsulates query logic for reusability.

### 8. Unit of Work Pattern (existing)
Manages transactions across repositories.

---

## Common Scenarios

### Scenario 1: Item Writer submits task for review

**Flow**:
```csharp
// Controller
[HttpPost("tasks/{taskId}/submit-for-review")]
public async Task<IActionResult> SubmitForReview(
    Guid taskId,
    [FromBody] SubmitForReviewDto dto)
{
    await taskAppService.SubmitForReviewAsync(
        taskId, 
        dto.ReviewerId, 
        GetCurrentUserId(), 
        HttpContext.RequestAborted);
    
    return Ok();
}

// Application Service
public async Task SubmitForReviewAsync(
    Guid taskId, 
    Guid reviewerId, 
    Guid userId, 
    CancellationToken ct)
{
    var task = await taskRepo.GetWithAllData(taskId, ct);
    
    if (!await authService.CanEditTask(task, userId, ct))
        throw new UnauthorizedException();
    
    // Domain method!
    task.SubmitForReview(reviewerId, userId);
    
    await taskRepo.Update(task, ct);
}

// Domain
public void SubmitForReview(Guid reviewerId, Guid submittedBy)
{
    ValidateStatusTransition(TaskStatus.Draft, TaskStatus.InReview);
    ValidateCurrentUser(submittedBy);
    
    Status = TaskStatus.InReview;
    ReviewerId = reviewerId;
    CurrentAssignment = new TaskAssignment(reviewerId, TaskRole.Reviewer);
    UpdatedOn = DateTimeOffset.UtcNow;
    
    RaiseDomainEvent(new TaskSubmittedForReviewEvent(Id, submittedBy, reviewerId));
}

// Event Handler
public class TaskSubmittedForReviewHandler : INotificationHandler<...>
{
    public async Task Handle(TaskSubmittedForReviewEvent evt, CancellationToken ct)
    {
        var reviewer = await userRepo.Get(evt.ReviewerId, ct);
        await emailService.SendReviewNotification(reviewer.Email, evt.TaskId);
        await notificationService.CreateInAppNotification(evt.ReviewerId, ...);
    }
}
```

### Scenario 2: Test Developer approves task for translation

**Flow**:
```csharp
// Domain
public void ApproveForTranslation(Guid approvedBy)
{
    ValidateStatusTransition(TaskStatus.InReview, TaskStatus.InTranslation);
    ValidateCurrentUser(approvedBy);
    
    if (Language != Language.DE)
        throw new InvalidOperationException("Only DE tasks can be approved for translation");
    
    Status = TaskStatus.InTranslation;
    UpdatedOn = DateTimeOffset.UtcNow;
    
    RaiseDomainEvent(new TaskApprovedForTranslationEvent(Id, TaskGroupId, approvedBy));
}

// Event Handler - AUTOMATIC FR/IT creation!
public class TaskApprovedForTranslationHandler : INotificationHandler<...>
{
    public async Task Handle(TaskApprovedForTranslationEvent evt, CancellationToken ct)
    {
        var deTask = await taskRepo.GetWithAllData(evt.TaskId, ct);
        
        // Create FR task
        var frTask = TaskEntity.CreateTranslationFrom(
            deTask, 
            Language.FR, 
            Guid.Empty); // Will be assigned later
        
        frTask.AssignTranslator(translatorId, systemUserId);
        await taskRepo.Add(frTask, ct);
        
        // Create IT task
        var itTask = TaskEntity.CreateTranslationFrom(
            deTask, 
            Language.IT, 
            Guid.Empty);
        
        itTask.AssignTranslator(translatorId, systemUserId);
        await taskRepo.Add(itTask, ct);
    }
}
```

### Scenario 3: Create new TestVersion revision

**Flow**:
```csharp
// Application Service
public async Task<TestVersionDto> CreateRevisionAsync(
    Guid originalVersionId,
    Guid userId,
    CancellationToken ct)
{
    // Use Domain Service for complex multi-aggregate operation
    var newVersion = await testVersionRevisionService.CreateRevision(
        originalVersionId, 
        userId, 
        ct);
    
    return mapper.Map<TestVersionDto>(newVersion);
}

// Domain Service
public class TestVersionRevisionService
{
    public async Task<TestVersionEntity> CreateRevision(
        Guid originalVersionId,
        Guid userId,
        CancellationToken ct)
    {
        var original = await repo.GetWithAllModules(originalVersionId, ct);
        
        // Domain method validates business rules
        var newVersion = original.CreateRevision(userId);
        
        // Deep copy all modules/tasks/fields/items
        foreach (var module in original.Modules)
        {
            var newModule = new ModuleEntity
            {
                ModuleNumber = module.ModuleNumber,
                ModuleName = module.ModuleName,
                Type = module.Type,
                Level = module.Level,
                Position = module.Position,
                TestVersionId = newVersion.Id
            };
            
            foreach (var taskGroup in module.TaskGroups)
            {
                var newTaskGroup = new TaskGroupEntity
                {
                    ModuleId = newModule.Id,
                    ScenarioId = taskGroup.ScenarioId,
                    Position = taskGroup.Position
                };
                
                foreach (var task in taskGroup.Tasks)
                {
                    var newTask = TaskEntity.CreateDraft(
                        task.TaskNumber,
                        task.Language,
                        task.ItemWriterId,
                        newTaskGroup.Id
                    );
                    
                    // Deep copy fields and items
                    foreach (var field in task.Fields)
                    {
                        var newField = CloneField(field, newTask);
                        newTask.Fields.Add(newField);
                    }
                    
                    newTaskGroup.Tasks.Add(newTask);
                }
                
                newModule.TaskGroups.Add(newTaskGroup);
            }
            
            newVersion.Modules.Add(newModule);
        }
        
        await repo.Add(newVersion, ct);
        
        return newVersion;
    }
}
```

### Scenario 4: Item Writer proposes new Scenario

**Flow**:
```csharp
// Domain
public static ScenarioProposalEntity ProposeNewScenario(
    Guid moduleId,
    string moduleNumber,
    Guid originalScenarioId,
    TranslatedText newScenarioText,
    Guid proposedByUserId,
    Language proposerLanguage)
{
    if (newScenarioText == null)
        throw new ArgumentNullException(nameof(newScenarioText));
    
    return new ScenarioProposalEntity
    {
        ModuleId = moduleId,
        ModuleNumber = moduleNumber,
        OriginalScenarioId = originalScenarioId,
        ProposalType = ScenarioProposalType.NewScenario,
        NewScenarioText = newScenarioText,
        ProposedByUserId = proposedByUserId,
        ProposerLanguage = proposerLanguage,
        Status = ScenarioProposalStatus.Pending
    };
}

public void Approve(Guid reviewerId)
{
    if (Status != ScenarioProposalStatus.Pending)
        throw new InvalidOperationException($"Cannot approve proposal in {Status} status");
    
    Status = ScenarioProposalStatus.Approved;
    ReviewedByUserId = reviewerId;
    ReviewedOn = DateTimeOffset.UtcNow;
    
    RaiseDomainEvent(new ScenarioProposalApprovedEvent(
        Id, 
        ModuleId, 
        OriginalScenarioId,
        NewScenarioText != null ? null : ExistingScenarioId, 
        reviewerId));
}

// Event Handler
public class ScenarioProposalApprovedHandler : INotificationHandler<...>
{
    public async Task Handle(ScenarioProposalApprovedEvent evt, CancellationToken ct)
    {
        var proposal = await proposalRepo.Get(evt.ProposalId, ct);
        
        Guid scenarioIdToUse;
        
        if (proposal.ProposalType == ScenarioProposalType.NewScenario)
        {
            // Create new scenario from proposal
            var newScenario = new ScenarioEntity
            {
                ActionFieldId = /* determine from context */,
                ScenarioText = proposal.NewScenarioText!
            };
            
            await scenarioRepo.Add(newScenario, ct);
            scenarioIdToUse = newScenario.Id;
        }
        else
        {
            scenarioIdToUse = proposal.ExistingScenarioId!.Value;
        }
        
        // Update all task groups in this module
        var taskGroups = await taskGroupRepo.GetByModuleAndScenario(
            evt.ModuleId, 
            evt.OriginalScenarioId, 
            ct);
        
        foreach (var taskGroup in taskGroups)
        {
            taskGroup.ChangeScenario(scenarioIdToUse);
        }
        
        await unitOfWork.CommitAsync(ct);
    }
}
```

---

## Query Examples

### Complex Query with DTOs (Query Service)

```csharp
public class TaskQueryService : ITaskQueryService
{
    private readonly FideDbContext _context;
    
    public async Task<List<TaskByGroupIdDto>> GetTasksByGroupAsync(
        Guid groupId,
        string? currentUserId,
        CancellationToken ct)
    {
        var tasks = await _context.Tasks
            .Include(t => t.TaskGroup)
                .ThenInclude(tg => tg.Scenario)
            .Include(t => t.CurrentAssignedUser)
            .Include(t => t.ItemWriter)
            .Include(t => t.Translator)
            .Include(t => t.Reviewer)
            .Where(t => t.TaskGroupId == groupId)
            .AsNoTracking() // Performance!
            .ToListAsync(ct);
        
        if (!tasks.Any()) return new List<TaskByGroupIdDto>();
        
        // Get related data
        var scenarioGroupId = tasks.First().TaskGroup.Scenario.GroupId;
        var languages = tasks.Select(t => t.Language).Distinct().ToList();
        
        var scenarios = await _context.Scenarios
            .Where(s => s.GroupId == scenarioGroupId && languages.Contains(s.Language))
            .Include(s => s.ActionField)
                .ThenInclude(a => a.Domain)
            .AsNoTracking()
            .ToListAsync(ct);
        
        // Project to DTOs
        var taskDtos = tasks.Select(t => 
        {
            var scenario = scenarios.First(s => s.Language == t.Language);
            
            return new TaskDto
            {
                Id = t.Id,
                TaskNumber = t.TaskNumber,
                Status = t.Status,
                Language = t.Language,
                Scenario = new ScenarioDto
                {
                    Id = scenario.Id,
                    Text = scenario.ScenarioText.GetTranslation(t.Language),
                    ActionField = scenario.ActionField.ActionFieldText.GetTranslation(t.Language),
                    Domain = scenario.ActionField.Domain.DomainText.GetTranslation(t.Language)
                },
                CanEdit = CanUserEditTask(t, currentUserId)
            };
        }).ToList();
        
        return new List<TaskByGroupIdDto>
        {
            new TaskByGroupIdDto
            {
                GroupId = groupId,
                Tasks = taskDtos,
                // ... other properties
            }
        };
    }
    
    private bool CanUserEditTask(TaskEntity task, string? userId)
    {
        if (string.IsNullOrEmpty(userId)) return false;
        
        var isInEditableStatus = task.Status == TaskStatus.Draft ||
                                  task.Status == TaskStatus.InRevision ||
                                  task.Status == TaskStatus.InTranslation ||
                                  task.Status == TaskStatus.InTranslationAfterReview;
        
        var isAssigned = task.CurrentAssignment.UserId.ToString() == userId; // Assuming string comparison
        
        return isInEditableStatus && isAssigned;
    }
}
```

---

## Performance Considerations

### 1. Lazy Loading vs Eager Loading

**Bad**:
```csharp
// N+1 problem
var tasks = await taskRepo.GetAll();
foreach (var task in tasks)
{
    // Each iteration = 1 query!
    var fields = task.Fields.ToList();
}
```

**Good**:
```csharp
// Single query with includes
var tasks = await _context.Tasks
    .Include(t => t.Fields)
        .ThenInclude(f => f.Items)
    .ToListAsync();
```

### 2. AsNoTracking for Read-Only

```csharp
// Query Service - read-only
public async Task<TaskDetailsDto> GetTaskDetails(Guid id, CancellationToken ct)
{
    return await _context.Tasks
        .AsNoTracking() // No change tracking = faster!
        .Where(t => t.Id == id)
        .Select(t => new TaskDetailsDto { ... })
        .FirstOrDefaultAsync(ct);
}
```

### 3. Projection to DTOs

**Bad**:
```csharp
// Loads entire entity into memory
var tasks = await _context.Tasks.ToListAsync();
return tasks.Select(t => new TaskDto { Id = t.Id, ... }).ToList();
```

**Good**:
```csharp
// Projects at database level
return await _context.Tasks
    .Select(t => new TaskDto { Id = t.Id, ... })
    .ToListAsync();
```

### 4. Batch Operations

```csharp
// Bad - N queries
foreach (var taskId in taskIds)
{
    var task = await repo.Get(taskId);
    task.Archive(userId);
    await repo.Update(task);
}

// Good - 1 query + batch update
var tasks = await _context.Tasks
    .Where(t => taskIds.Contains(t.Id))
    .ToListAsync();

foreach (var task in tasks)
{
    task.Archive(userId);
}

await _context.SaveChangesAsync();
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Migration scripts reviewed
- [ ] Rollback plan documented
- [ ] Performance testing completed
- [ ] Code review approved
- [ ] Documentation updated

### Deployment Steps
1. Backup production database
2. Deploy application in maintenance mode
3. Run migrations
4. Verify data integrity
5. Run smoke tests
6. Exit maintenance mode
7. Monitor for errors

### Post-Deployment
- [ ] Verify all endpoints working
- [ ] Check domain event processing
- [ ] Monitor performance metrics
- [ ] Verify audit logs
- [ ] Check error logs
- [ ] User acceptance testing

### Rollback Procedure
1. Put system in maintenance mode
2. Rollback database migration: `dotnet ef database update <PreviousMigration>`
3. Deploy previous application version
4. Verify functionality
5. Exit maintenance mode
6. Document rollback reason

---

## Monitoring & Observability

### Key Metrics

**Domain Events**:
- Event processing time
- Failed event handlers
- Event queue depth

**Aggregate Operations**:
- Average load time per aggregate
- Save operation duration
- Concurrent modification conflicts

**Performance**:
- API response times
- Database query performance
- Memory usage

### Logging Strategy

```csharp
// Domain Event Handler
public class TaskSubmittedForReviewHandler : INotificationHandler<...>
{
    private readonly ILogger<TaskSubmittedForReviewHandler> _logger;
    
    public async Task Handle(TaskSubmittedForReviewEvent evt, CancellationToken ct)
    {
        _logger.LogInformation(
            "Processing TaskSubmittedForReview: TaskId={TaskId}, ReviewerId={ReviewerId}",
            evt.TaskId,
            evt.ReviewerId);
        
        try
        {
            await emailService.SendNotification(...);
            
            _logger.LogInformation(
                "Successfully processed TaskSubmittedForReview: TaskId={TaskId}",
                evt.TaskId);
        }
        catch (Exception ex)
        {
            _logger.LogError(
                ex,
                "Failed to process TaskSubmittedForReview: TaskId={TaskId}",
                evt.TaskId);
            throw;
        }
    }
}
```

---

## Future Enhancements

### 1. CQRS with Separate Read Model
```csharp
// Command side - write model
public class TaskEntity : EntityBase { ... }

// Query side - read model (denormalized)
public class TaskReadModel
{
    public Guid Id { get; set; }
    public string TaskNumber { get; set; }
    public TaskStatus Status { get; set; }
    public string ScenarioText { get; set; } // Denormalized!
    public string DomainName { get; set; } // Denormalized!
    // ... all data needed for queries
}

// Event handler syncs read model
public class TaskSubmittedForReviewHandler
{
    public async Task Handle(TaskSubmittedForReviewEvent evt)
    {
        // Update write model
        var task = await taskRepo.Get(evt.TaskId);
        task.SubmitForReview(...);
        await taskRepo.Update(task);
        
        // Update read model
        var readModel = await readModelRepo.Get(evt.TaskId);
        readModel.Status = TaskStatus.InReview;
        readModel.ReviewerName = reviewer.FullName; // Denormalized!
        await readModelRepo.Update(readModel);
    }
}
```

### 2. Event Sourcing (Advanced)
Store all changes as events instead of current state.

### 3. Integration Events
Publish events to external systems (RabbitMQ, Azure Service Bus).

### 4. Saga Pattern
For complex multi-step processes across aggregates.

### 5. Specification Pattern
```csharp
public class TasksByStatusSpecification : Specification<TaskEntity>
{
    private readonly TaskStatus _status;
    
    public override Expression<Func<TaskEntity, bool>> ToExpression()
    {
        return task => task.Status == _status;
    }
}

// Usage
var spec = new TasksByStatusSpecification(TaskStatus.InReview)
    .And(new TasksAssignedToUserSpecification(userId));

var tasks = await repo.Find(spec);
```

---

## FAQs

### Q: Mikor használjunk Domain Service vs Application Service?
**A**: Domain Service akkor, ha a business logic több aggregate-et érint, de még mindig domain logic. Application Service csak orchestration-re.

### Q: Hogyan kezeljük a transaction-öket több aggregate között?
**A**: Domain Event-ekkel eventual consistency-t érünk el. Ha strong consistency kell, az egy jel hogy rossz az aggregate boundary.

### Q: Mi van ha egy Domain Event handler elszáll?
**A**: Retry policy + DLQ (Dead Letter Queue). Kritikus event-ek esetén Outbox Pattern.

### Q: Hogyan tesztelünk Domain Event-eket?
**A**: Unit testben ellenőrizzük hogy az event raised-e. Integration testben az egész flow-t (event handler-rel együtt).

### Q: Kell-e minden entitásnak Aggregate Root-nak lennie?
**A**: NEM! Csak azoknak, amiknek független lifecycle-juk van és consistency boundary-t képeznek.

### Q: Mi a különbség Entity és Value Object között?
**A**: Entity-nek van identity-je (Id), Value Object-nek nincs, és immutable. TranslatedText = VO, TaskEntity = Entity.

### Q: Hogyan kezeljük a validációt?
**A**: 3 szint:
1. DTO validáció (FluentValidation) - Application layer
2. Business rule validáció - Domain layer (aggregate methods-ban)
3. Database constraints - Infrastructure layer

### Q: Mit csinálunk ha egy aggregate túl nagy lesz?
**A**: Split into multiple aggregates. Pl. Task és TaskGroup külön aggregate-ek lehetnének.

---

## Glossary

**Aggregate**: Entitások csoportja egy consistency boundary-vel, Aggregate Root-tal
**Aggregate Root**: Az aggregate fő entitása, amin keresztül minden módosítás megy
**Value Object**: Immutable objektum identity nélkül (pl. TranslatedText)
**Domain Event**: Valami történt esemény a domain-ben
**Domain Service**: Business logic ami nem tartozik egy aggregate-hez
**Application Service**: Orchestration layer, nem tartalmaz business logic-ot
**Repository**: Data access abstraction aggregate root-okhoz
**Unit of Work**: Transaction management pattern
**CQRS**: Command Query Responsibility Segregation - írás/olvasás szétválasztása
**Event Sourcing**: State tárolása event-ek sorozataként
**Invariant**: Business rule ami mindig igaz kell legyen egy aggregate-en belül
**Bounded Context**: Domain egy része saját modellel és ubiquitous language-dzsel

---

## References

- **Domain-Driven Design** by Eric Evans
- **Implementing Domain-Driven Design** by Vaughn Vernon
- **Clean Architecture** by Robert C. Martin
- **Patterns of Enterprise Application Architecture** by Martin Fowler
- Microsoft Docs: https://docs.microsoft.com/en-us/dotnet/architecture/microservices/

---

## Contact & Support

Ha kérdésed van a refaktorálással kapcsolatban:
1. Nézd meg ezt a dokumentumot
2. Ellenőrizd a code artifact-okat
3. Futtasd a unit testeket példákért
4. Kérdezz a team-től

**Fontos**: Ez egy élő dokumentum. Ahogy haladsz a refaktorálással, frissítsd ezt a summary-t az új tanulságokkal!