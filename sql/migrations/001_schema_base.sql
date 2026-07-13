SET NOCOUNT ON;

IF OBJECT_ID('dbo.Aves', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Aves (
        Id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Aves PRIMARY KEY,
        Nombre NVARCHAR(50) NOT NULL,
        Color NVARCHAR(100) NULL,
        Notas NVARCHAR(500) NULL,
        FechaRegistro DATETIME2(3) NOT NULL
            CONSTRAINT DF_Aves_FechaRegistro DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF OBJECT_ID('dbo.BitacoraAves', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.BitacoraAves (
        Id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_BitacoraAves PRIMARY KEY,
        Fecha DATETIME2(3) NOT NULL
            CONSTRAINT DF_BitacoraAves_Fecha DEFAULT SYSUTCDATETIME(),
        Categoria NVARCHAR(50) NOT NULL,
        Accion NVARCHAR(300) NOT NULL,
        Valor_Numerico FLOAT NULL,
        Estado_Observado NVARCHAR(50) NULL,
        Confianza_IA FLOAT NULL,
        Notas NVARCHAR(1000) NULL,
        AveId INT NULL,
        TrackId INT NULL
    );
END;
GO
