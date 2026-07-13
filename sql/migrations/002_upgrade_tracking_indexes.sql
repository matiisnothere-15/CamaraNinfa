SET NOCOUNT ON;

IF COL_LENGTH('dbo.Aves', 'Color') IS NULL
    ALTER TABLE dbo.Aves ADD Color NVARCHAR(100) NULL;

IF COL_LENGTH('dbo.Aves', 'Notas') IS NULL
    ALTER TABLE dbo.Aves ADD Notas NVARCHAR(500) NULL;

IF COL_LENGTH('dbo.Aves', 'FechaRegistro') IS NULL
    ALTER TABLE dbo.Aves ADD FechaRegistro DATETIME2(3) NULL;
GO

UPDATE dbo.Aves
SET FechaRegistro = SYSUTCDATETIME()
WHERE FechaRegistro IS NULL;

ALTER TABLE dbo.Aves ALTER COLUMN FechaRegistro DATETIME2(3) NOT NULL;

IF NOT EXISTS (
    SELECT 1
    FROM sys.default_constraints dc
    INNER JOIN sys.columns c
        ON c.default_object_id = dc.object_id
    WHERE c.object_id = OBJECT_ID('dbo.Aves') AND c.name = 'FechaRegistro'
)
    ALTER TABLE dbo.Aves ADD CONSTRAINT DF_Aves_FechaRegistro
        DEFAULT SYSUTCDATETIME() FOR FechaRegistro;
GO

IF COL_LENGTH('dbo.BitacoraAves', 'AveId') IS NULL
    ALTER TABLE dbo.BitacoraAves ADD AveId INT NULL;

IF COL_LENGTH('dbo.BitacoraAves', 'TrackId') IS NULL
    ALTER TABLE dbo.BitacoraAves ADD TrackId INT NULL;
GO

UPDATE dbo.BitacoraAves SET Accion = 'SinAccion' WHERE Accion IS NULL;
ALTER TABLE dbo.BitacoraAves ALTER COLUMN Accion NVARCHAR(300) NOT NULL;
ALTER TABLE dbo.BitacoraAves ALTER COLUMN Notas NVARCHAR(1000) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_BitacoraAves_Aves'
)
BEGIN
    ALTER TABLE dbo.BitacoraAves WITH CHECK
    ADD CONSTRAINT FK_BitacoraAves_Aves
        FOREIGN KEY (AveId) REFERENCES dbo.Aves(Id) ON DELETE SET NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_BitacoraAves_Fecha' AND object_id = OBJECT_ID('dbo.BitacoraAves')
)
    CREATE INDEX IX_BitacoraAves_Fecha ON dbo.BitacoraAves (Fecha DESC);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_BitacoraAves_Categoria_Accion_Fecha'
      AND object_id = OBJECT_ID('dbo.BitacoraAves')
)
    CREATE INDEX IX_BitacoraAves_Categoria_Accion_Fecha
        ON dbo.BitacoraAves (Categoria, Accion, Fecha DESC);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_BitacoraAves_AveId_Fecha'
      AND object_id = OBJECT_ID('dbo.BitacoraAves')
)
    CREATE INDEX IX_BitacoraAves_AveId_Fecha
        ON dbo.BitacoraAves (AveId, Fecha DESC);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_Aves_Nombre' AND object_id = OBJECT_ID('dbo.Aves')
)
    CREATE INDEX IX_Aves_Nombre ON dbo.Aves (Nombre);
GO
