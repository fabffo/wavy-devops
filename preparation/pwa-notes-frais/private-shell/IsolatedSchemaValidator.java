import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.*;
import java.util.*;
import jakarta.persistence.*;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationState;
import org.hibernate.boot.MetadataSources;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;

/** Standalone control tool. Never boots Spring, business services or schedulers. */
public final class IsolatedSchemaValidator {
    static String stage = "input";
    static void require(boolean condition) {
        if (!condition) throw new IllegalStateException("Validation refused");
    }
    public static void main(String[] args) {
        try {
            require(args.length == 3);
            require(args[0].matches("[a-z][a-z0-9_]*") && args[1].matches("validator_[a-f0-9]+"));
            String password = new BufferedReader(new InputStreamReader(System.in)).readLine();
            require(password != null && password.matches("[a-f0-9]{64}"));
            String url = "jdbc:postgresql://127.0.0.1:5432/" + args[0] + "?connectTimeout=5&socketTimeout=30";
            stage = "sql-permissions";
            boolean authenticationDenied=false;
            try (var invalid=DriverManager.getConnection(url,args[1],"invalid-fixture-password")) { }
            catch (SQLException e) { authenticationDenied="28P01".equals(e.getSQLState()); }
            require(authenticationDenied);
            try (Connection c = DriverManager.getConnection(url, args[1], password);
                 Statement s = c.createStatement()) {
                try (ResultSet r = s.executeQuery("SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user")) {
                    require(r.next()); for (int i=1;i<=4;i++) require(!r.getBoolean(i));
                }
                try (ResultSet r = s.executeQuery("SELECT count(*) FROM information_schema.role_table_grants WHERE grantee=current_user AND privilege_type <> 'SELECT'")) {
                    require(r.next() && r.getInt(1)==0);
                }
                // Prove actual permissions even if the read-only default is turned off.
                s.execute("SET default_transaction_read_only=off");
                for (String sql : List.of("CREATE TABLE public.__validator_forbidden(id int)",
                        "CREATE TEMP TABLE __validator_forbidden(id int)",
                        "DELETE FROM public.flyway_schema_history WHERE false",
                        "SELECT * FROM public.note_frais LIMIT 0")) {
                    boolean denied=false;
                    try { s.execute(sql); } catch (SQLException e) {
                        denied = "42501".equals(e.getSQLState());
                    }
                    require(denied);
                }
                s.execute("SET default_transaction_read_only=on");
            }
            stage = "flyway";
            Flyway flyway = Flyway.configure().dataSource(url,args[1],password)
                .locations("classpath:db/migration/common", "classpath:db/migration/postgresql")
                .schemas("public").table("flyway_schema_history").baselineOnMigrate(false)
                .cleanDisabled(true).outOfOrder(false).ignoreMigrationPatterns(new String[0]).load();
            require(flyway.validateWithResult().validationSuccessful);
            int migrations=0;
            for (var migration : flyway.info().all()) {
                if (migration.getState() == MigrationState.BASELINE) {
                    require("0".equals(migration.getVersion().toString()));
                } else {
                    require(migration.getState() == MigrationState.SUCCESS); migrations++;
                }
            }
            require(migrations==20);
            stage = "jpa";
            var builder = new StandardServiceRegistryBuilder()
                .applySetting("hibernate.connection.url",url)
                .applySetting("hibernate.connection.username",args[1])
                .applySetting("hibernate.connection.password",password)
                .applySetting("hibernate.connection.driver_class","org.postgresql.Driver")
                .applySetting("hibernate.hbm2ddl.auto","validate")
                .applySetting("hibernate.default_schema","public")
                .applySetting("hibernate.jdbc.time_zone","UTC")
                .applySetting("hibernate.show_sql","false")
                .applySetting("hibernate.physical_naming_strategy","org.hibernate.boot.model.naming.PhysicalNamingStrategySnakeCaseImpl")
                .applySetting("hibernate.implicit_naming_strategy","org.springframework.boot.hibernate.SpringImplicitNamingStrategy");
            var registry=builder.build();
            int entities=0;
            try {
                var sources=new MetadataSources(registry);
                var converters=new ArrayList<Class<?>>();
                Path root=Path.of(args[2]);
                try (var files=Files.walk(root.resolve("fr/wavy/factures"))) {
                    for (Path file : files.filter(p -> p.toString().endsWith(".class")).sorted().toList()) {
                        String name=root.relativize(file).toString().replace('/', '.').replaceAll("\\.class$", "");
                        Class<?> cls=Class.forName(name,false,IsolatedSchemaValidator.class.getClassLoader());
                        if (cls.isAnnotationPresent(Entity.class) || cls.isAnnotationPresent(Embeddable.class)
                                || cls.isAnnotationPresent(MappedSuperclass.class)) {
                            sources.addAnnotatedClass(cls);
                            if (cls.isAnnotationPresent(Entity.class)) entities++;
                        }
                        if (cls.isAnnotationPresent(Converter.class)) {
                            converters.add(cls);
                        }
                    }
                }
                require(entities==23);
                var metadata=sources.getMetadataBuilder();
                for (var cls:converters) metadata.applyAttributeConverter((Class)cls,cls.getAnnotation(Converter.class).autoApply());
                try (var factory=metadata.build().buildSessionFactory()) { require(factory.isOpen()); }
            } finally { StandardServiceRegistryBuilder.destroy(registry); }
            System.out.println("WAVY_VALIDATION_OK migrations="+migrations+" entities="+entities);
        } catch (Throwable error) {
            // Never log exception messages, URLs or credentials from dependencies.
            System.out.println("WAVY_VALIDATION_FAILED stage="+stage);
            System.exit(1);
        }
    }
}
